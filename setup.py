#!/usr/bin/env python3
"""
Setup script for Thai Election Ballot OCR.

Install with:
    pip install -e .

Or from PyPI (when published):
    pip install thai-ballot-ocr
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read version
version_file = Path(__file__).parent / "version.py"
version_dict = {}
exec(version_file.read_text(), version_dict)
__version__ = version_dict.get("__version__", "1.1.0")

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="thai-ballot-ocr",
    version=__version__,
    author="Thai Election Ballot OCR Contributors",
    author_email="",
    description="Automated ballot verification system for Thai elections using AI Vision OCR",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/election",
    license="MIT",
    packages=find_packages(exclude=["tests", "tests.*"]),
    py_modules=[
        "ballot_ocr",
        "batch_processor",
        "web_ui",
        "ect_api",
        "metadata_parser",
        "config",
        "logging_config",
        "cli",
        "version",
        "gdrivedl",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Image Recognition",
        "Topic :: Sociology",
    ],
    python_requires=">=3.11",
    install_requires=[
        "requests>=2.28.0",
        "tenacity>=8.0.0",
        "gradio>=4.0.0",
        "reportlab>=4.0.0",
        "Pillow>=9.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "ruff>=0.1.0",
            "pyright>=0.1.0",
            "pre-commit>=3.0.0",
        ],
        "tesseract": [
            "pytesseract>=0.3.10",
        ],
        "gdrive": [
            "google-api-python-client>=2.0.0",
            "google-auth-oauthlib>=1.0.0",
            "gdown>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ballot-ocr=cli:main",
            "thai-ballot-ocr=cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="thai election ballot ocr ai vision verification",
)
