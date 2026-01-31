from setuptools import setup, find_packages

setup(
    name="windows-manager",
    version="0.1.0",
    description="A lean combined system manager for Windows",
    author="",
    author_email="",
    packages=find_packages(),
    install_requires=[
        "PySide6>=6.6.0",
        "psutil>=5.9.0",
        "pywin32>=306",
    ],
    python_requires=">=3.13",
    entry_points={
        "console_scripts": [
            "winmanager=src.main:main",
        ],
    },
)
