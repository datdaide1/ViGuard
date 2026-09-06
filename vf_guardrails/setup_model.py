import os
import urllib.request
import sys
import time

def download_with_retry(url, dest_path):
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries} to download from: {url}")
            
            def progress_callback(read_bytes, total_bytes):
                if total_bytes > 0:
                    percent = (read_bytes / total_bytes) * 100
                    percent = min(100.0, percent)
                    sys.stdout.write(f"\r   Progress: {percent:.1f}% ({read_bytes / (1024*1024):.1f} MB / {total_bytes / (1024*1024):.1f} MB)")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"\r   Downloaded: {read_bytes / (1024*1024):.1f} MB")
                    sys.stdout.flush()

            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=45) as response, open(dest_path, 'wb') as out_file:
                total_size = int(response.info().get('Content-Length', 0))
                block_size = 1024 * 16  # 16 KB chunks
                read_so_far = 0
                while True:
                    block = response.read(block_size)
                    if not block:
                        break
                    read_so_far += len(block)
                    out_file.write(block)
                    progress_callback(read_so_far, total_size)
            sys.stdout.write("\n")
            print("-> Download completed successfully!")
            return True
        except Exception as e:
            print(f"\n   Error on attempt {attempt}: {e}")
            if attempt < max_retries:
                print("   Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return False

def main():
    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")
    os.makedirs(model_dir, exist_ok=True)

    print("=" * 80)
    print("SETTING UP PHOBERT SEMANTIC EMBEDDING MODEL OFFLINE")
    print("=" * 80)

    # 1. Download and save Tokenizer locally
    try:
        from transformers import AutoTokenizer
        print("1. Downloading and saving Tokenizer configuration...")
        tokenizer_name = "dangvantuan/vietnamese-embedding"
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        tokenizer.save_pretrained(model_dir)
        print("-> Tokenizer saved successfully in 'model/' directory.")
    except ImportError:
        print("Error: 'transformers' library not found. Please install dependencies first.")
        sys.exit(1)
    except Exception as e:
        print(f"Error downloading Tokenizer: {e}")
        sys.exit(1)

    # 2. Download model_quantized.onnx directly from Hugging Face (much smaller and faster)
    onnx_file_path = os.path.join(model_dir, "model.onnx")
    onnx_url = "https://huggingface.co/laituanmanh32/vietnamese-embedding-onnx/resolve/main/onnx/model_quantized.onnx"
    
    print("\n2. Downloading Quantized ONNX model weights (optimized)...")
    print("This will download a smaller, faster quantized version of the model.")
    
    success = download_with_retry(onnx_url, onnx_file_path)
    if not success:
        # Fallback to model-int8.onnx if quantized.onnx is missing or fails
        print("Trying fallback to model-int8.onnx...")
        onnx_url_fallback = "https://huggingface.co/laituanmanh32/vietnamese-embedding-onnx/resolve/main/onnx/model-int8.onnx"
        success = download_with_retry(onnx_url_fallback, onnx_file_path)
        
    if not success:
        print("\nFatal Error: Failed to download ONNX model weights after multiple attempts.")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("OFFLINE MODEL SETUP COMPLETED SUCCESSFULLY!")
    print("All model files are prepared in the 'model/' directory.")
    print("=" * 80)

if __name__ == "__main__":
    main()
