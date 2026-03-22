import torch
import undetected_chromedriver as uc
import whisper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def print_separator():
    print("\n" + "=" * 50 + "\n")


def test_pytorch_cuda():
    print("🧪 TESTING PYTORCH & CUDA...")
    print(f"PyTorch Version: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_available}")

    if cuda_available:
        print(f"GPU Device: {torch.cuda.get_device_name(0)}")
        # Test a simple tensor operation on GPU
        x = torch.rand(5, 3).cuda()
        print("✅ Success: Tensor successfully loaded to GPU.")
    else:
        print("⚠️ Warning: CUDA is not available. PyTorch is using CPU.")


def test_scraping_tools():
    print("🧪 TESTING SCRAPING TOOLS (BeautifulSoup)...")
    html_doc = "<html><head><title>The Scraper</title></head><body><p class='title'><b>Success!</b></p></body></html>"
    soup = BeautifulSoup(html_doc, "html.parser")
    print(f"BeautifulSoup parsed title: {soup.title.string}")
    print("✅ Success: BeautifulSoup is working.")


def test_whisper():
    print("🧪 TESTING WHISPER AI...")
    model_size = "tiny"  # Using tiny model for quick download and test
    print(f"Loading Whisper '{model_size}' model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model = whisper.load_model(model_size, device=device)
        print(f"✅ Success: Whisper loaded on {device.upper()}.")
    except Exception as e:
        print(f"❌ Whisper failed to load: {e}")


if __name__ == "__main__":
    print_separator()
    print("🚀 STARTING ENVIRONMENT DIAGNOSTICS")
    print_separator()

    test_pytorch_cuda()
    print_separator()

    test_scraping_tools()
    print_separator()

    test_whisper()
    print_separator()

    print("Diagnostics complete! You are ready to scrape. 🕷️")
