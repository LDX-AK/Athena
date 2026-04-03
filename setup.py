from setuptools import setup, find_packages

setup(
    name="athena-aibot",
    version="1.0.0",
    description="Athena AI-Bot — Multi-Exchange Scalping",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "ccxt>=4.3.0",
        "lightgbm>=4.3.0",
        "scikit-learn>=1.4.0",
        "numpy>=1.26.0",
        "pandas>=2.2.0",
        "streamlit>=1.35.0",
        "python-dotenv>=1.0.0",
        "redis>=5.0.0",
        "aiohttp>=3.9.0",
    ],
    entry_points={
        "console_scripts": [
            "athena=athena.__main__:main",
        ]
    },
)
