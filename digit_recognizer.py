#!/usr/bin/env python3
"""
Handwritten digit recognition for Thai ballot vote extraction.

This module provides tools for fine-tuning digit recognition models
on ballot-specific handwritten numbers.

TRAINING DATA REQUIREMENTS:
- 100-500 labeled ballot regions with vote counts
- Images should be cropped to individual number regions
- Annotations in format: {"image_path": "123", "label": "123"}

USAGE:
    # Train new model (when data is available)
    python digit_recognizer.py --train --data ./labeled_digits/ --output ./model/

    # Use trained model for inference
    python digit_recognizer.py --predict --model ./model/ --image crop.png
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from PIL import Image
    import torchvision.transforms as transforms
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class DigitRecognitionResult:
    """Result from digit recognition."""
    text: str
    confidence: float
    digits: List[Tuple[str, float]]  # List of (digit, confidence)


class SimpleDigitCNN(nn.Module if TORCH_AVAILABLE else object):
    """
    Simple CNN for handwritten digit recognition.

    Architecture based on LeNet-5, suitable for 28x28 grayscale images.
    Can classify digits 0-9 and handle multi-digit sequences via CTC loss.
    """

    def __init__(self, num_classes: int = 11):  # 0-9 + blank for CTC
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed")

        super().__init__()

        self.features = nn.Sequential(
            # Conv block 1
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            # Conv block 2
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            # Conv block 3
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 3 * 3, 256),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


class CRNN(nn.Module if TORCH_AVAILABLE else object):
    """
    CNN + RNN for recognizing number sequences.

    Uses CNN for feature extraction and LSTM for sequence modeling.
    Outputs character probabilities for CTC decoding.
    """

    def __init__(self, num_classes: int = 11, hidden_size: int = 128):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed")

        super().__init__()

        # CNN backbone
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)),  # Preserve width for sequence
        )

        # RNN for sequence
        self.lstm = nn.LSTM(256, hidden_size, bidirectional=True, batch_first=True)

        # Output layer
        self.fc = nn.Linear(hidden_size * 2, num_classes)

    def forward(self, x):
        # CNN features
        conv = self.cnn(x)  # [B, C, H, W]

        # Reshape for LSTM: [B, W, C*H]
        b, c, h, w = conv.size()
        conv = conv.permute(0, 3, 1, 2)  # [B, W, C, H]
        conv = conv.contiguous().view(b, w, c * h)

        # LSTM
        lstm_out, _ = self.lstm(conv)

        # Output
        output = self.fc(lstm_out)
        output = torch.nn.functional.log_softmax(output, dim=2)

        return output


class DigitDataset(Dataset if TORCH_AVAILABLE else object):
    """Dataset for training digit recognition."""

    def __init__(self, data_dir: str, transform=None):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed")

        self.data_dir = Path(data_dir)
        self.transform = transform or transforms.Compose([
            transforms.Grayscale(),
            transforms.Resize((28, 28)),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])

        # Load annotations
        self.samples = []
        annotations_file = self.data_dir / "annotations.txt"
        if annotations_file.exists():
            with open(annotations_file) as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) == 2:
                        self.samples.append((parts[0], parts[1]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]

        # Load image
        img = Image.open(self.data_dir / img_path)
        img = self.transform(img)

        # Convert label to tensor
        label_tensor = torch.tensor([int(c) for c in label])

        return img, label_tensor


class DigitRecognizer:
    """
    Main class for digit recognition on ballot images.

    Can use either:
    1. Simple CNN for isolated single digits
    2. CRNN for multi-digit numbers
    """

    def __init__(self, model_path: Optional[str] = None, model_type: str = "cnn"):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed. Run: pip install torch")
        if not PIL_AVAILABLE:
            raise ImportError("PIL not installed. Run: pip install Pillow")

        self.model_type = model_type
        self.device = torch.device("cuda" if torch.cuda.is_available() else
                                   "mps" if torch.backends.mps.is_available() else
                                   "cpu")

        # Initialize model
        if model_type == "cnn":
            self.model = SimpleDigitCNN()
        else:
            self.model = CRNN()

        self.model.to(self.device)

        # Load weights if provided
        if model_path and os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
            self.model.eval()
            print(f"Loaded model from {model_path}")
        else:
            print("No model loaded. Train first or provide model_path.")

        # Transforms
        self.transform = transforms.Compose([
            transforms.Grayscale(),
            transforms.Resize((28, 28)),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])

    def train(self, data_dir: str, epochs: int = 10, lr: float = 0.001,
              output_path: str = "./digit_model.pt"):
        """
        Train the model on labeled data.

        Args:
            data_dir: Directory containing images and annotations.txt
            epochs: Number of training epochs
            lr: Learning rate
            output_path: Where to save the trained model
        """
        dataset = DigitDataset(data_dir, self.transform)
        dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)

        self.model.train()

        for epoch in range(epochs):
            total_loss = 0
            correct = 0
            total = 0

            for images, labels in dataloader:
                images = images.to(self.device)
                labels = labels.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(images)

                # For simple CNN
                loss = criterion(outputs, labels.squeeze())
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                _, predicted = outputs.max(1)
                total += labels.size(0)
                correct += predicted.eq(labels.squeeze()).sum().item()

            accuracy = 100 * correct / total if total > 0 else 0
            print(f"Epoch {epoch+1}/{epochs}: Loss={total_loss:.4f}, Accuracy={accuracy:.1f}%")

        # Save model
        torch.save(self.model.state_dict(), output_path)
        print(f"Model saved to {output_path}")

    def predict(self, image_path: str) -> DigitRecognitionResult:
        """
        Predict digits in an image.

        Args:
            image_path: Path to image containing handwritten number

        Returns:
            DigitRecognitionResult with prediction and confidence
        """
        self.model.eval()

        # Load and preprocess
        img = Image.open(image_path)
        img_tensor = self.transform(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(img_tensor)
            probs = torch.softmax(outputs, dim=1)
            confidence, predicted = probs.max(1)

            digit = predicted.item()
            conf = confidence.item()

        return DigitRecognitionResult(
            text=str(digit),
            confidence=conf,
            digits=[(str(digit), conf)]
        )

    def predict_multi_digit(self, image_path: str, max_digits: int = 5) -> DigitRecognitionResult:
        """
        Predict multi-digit numbers from an image.

        This method segments the image into individual digits and
        recognizes each one separately.

        Args:
            image_path: Path to image containing multi-digit number
            max_digits: Maximum number of digits to extract

        Returns:
            DigitRecognitionResult with combined prediction
        """
        # Load image
        img = Image.open(image_path).convert('L')

        # Simple segmentation by splitting into equal parts
        width, height = img.size
        digit_width = width // max_digits

        digits = []
        for i in range(max_digits):
            # Crop digit region
            left = i * digit_width
            right = (i + 1) * digit_width
            crop = img.crop((left, 0, right, height))

            # Save temp and predict
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                crop.save(tmp.name)
                result = self.predict(tmp.name)
                os.unlink(tmp.name)

            if result.confidence > 0.5:  # Filter low confidence
                digits.append(result)

        # Combine results
        if digits:
            text = ''.join(d.text for d in digits)
            avg_conf = sum(d.confidence for d in digits) / len(digits)
            digit_list = [(d.text, d.confidence) for d in digits]
        else:
            text = ""
            avg_conf = 0.0
            digit_list = []

        return DigitRecognitionResult(
            text=text,
            confidence=avg_conf,
            digits=digit_list
        )


def create_training_template(output_dir: str):
    """
    Create a template directory structure for training data.

    Directory structure:
    output_dir/
        annotations.txt  # Format: image_path\\tlabel
        images/
            001.png
            002.png
            ...
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "images").mkdir(exist_ok=True)

    # Create sample annotations file
    with open(output_path / "annotations.txt", "w") as f:
        f.write("# Format: image_path\\tlabel\\n")
        f.write("# Example:\\n")
        f.write("# images/001.png\\t123\\n")
        f.write("# images/002.png\\t45\\n")

    print(f"Created training data template at {output_dir}")
    print("Add your labeled images and annotations to train.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Digit recognition for ballots")
    parser.add_argument("--train", action="store_true", help="Train model")
    parser.add_argument("--predict", action="store_true", help="Predict digits")
    parser.add_argument("--template", action="store_true", help="Create training template")
    parser.add_argument("--data", type=str, help="Training data directory")
    parser.add_argument("--model", type=str, help="Model path (for loading/saving)")
    parser.add_argument("--image", type=str, help="Image to predict")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")

    args = parser.parse_args()

    if args.template:
        output_dir = args.data or "./digit_training_data"
        create_training_template(output_dir)
        return

    if args.train:
        if not args.data:
            print("Error: --data required for training")
            return

        recognizer = DigitRecognizer(model_type="cnn")
        recognizer.train(args.data, epochs=args.epochs,
                        output_path=args.model or "./digit_model.pt")
        return

    if args.predict:
        if not args.image:
            print("Error: --image required for prediction")
            return

        recognizer = DigitRecognizer(model_path=args.model)
        result = recognizer.predict(args.image)
        print(f"Prediction: {result.text} (confidence: {result.confidence:.2%})")
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
