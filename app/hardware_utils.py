"""
Hardware Detection and Requirements Management for AI Settings
"""
import subprocess
import logging
import os
import re

logger = logging.getLogger(__name__)


def detect_gpu_info():
    """
    Detect NVIDIA GPU information
    Returns dict with gpu_detected, gpu_name, vram_mb, cuda_version
    """
    result = {
        'gpu_detected': False,
        'gpu_name': None,
        'vram_mb': 0,
        'vram_gb': 0,
        'cuda_version': None,
        'driver_version': None,
        'nvidia_smi_available': False
    }
    
    try:
        # Check if nvidia-smi is available
        nvidia_smi_check = subprocess.run(
            ['which', 'nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if nvidia_smi_check.returncode != 0:
            logger.info("[Hardware] nvidia-smi not found")
            return result
        
        result['nvidia_smi_available'] = True
        
        # Get GPU name and VRAM
        gpu_query = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if gpu_query.returncode == 0 and gpu_query.stdout.strip():
            gpu_line = gpu_query.stdout.strip().split('\n')[0]  # First GPU only
            parts = gpu_line.split(',')
            if len(parts) >= 2:
                result['gpu_detected'] = True
                result['gpu_name'] = parts[0].strip()
                result['vram_mb'] = int(float(parts[1].strip()))
                result['vram_gb'] = round(result['vram_mb'] / 1024, 1)
        
        # Get driver and CUDA version
        driver_query = subprocess.run(
            ['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if driver_query.returncode == 0 and driver_query.stdout.strip():
            result['driver_version'] = driver_query.stdout.strip()
        
        # Get CUDA version from nvidia-smi
        cuda_query = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if cuda_query.returncode == 0:
            # Parse CUDA version from output
            match = re.search(r'CUDA Version:\s+(\d+\.\d+)', cuda_query.stdout)
            if match:
                result['cuda_version'] = match.group(1)
        
        logger.info(f"[Hardware] GPU detected: {result['gpu_name']} ({result['vram_gb']}GB VRAM)")
        
    except Exception as e:
        logger.error(f"[Hardware] Error detecting GPU: {e}")
    
    return result


def check_ollama_cuda_support():
    """
    Check if Ollama has CUDA support libraries
    """
    result = {
        'cuda_libs_found': False,
        'cuda_version': None,
        'lib_paths': []
    }
    
    try:
        ollama_lib_path = '/usr/local/lib/ollama'
        
        if not os.path.exists(ollama_lib_path):
            logger.info("[Hardware] Ollama lib path not found")
            return result
        
        # Check for CUDA library directories
        cuda_dirs = []
        for item in os.listdir(ollama_lib_path):
            if 'cuda' in item.lower():
                full_path = os.path.join(ollama_lib_path, item)
                if os.path.isdir(full_path):
                    cuda_dirs.append(full_path)
                    result['lib_paths'].append(full_path)
        
        if cuda_dirs:
            result['cuda_libs_found'] = True
            # Try to determine version from directory name
            for d in cuda_dirs:
                if 'cuda_v12' in d:
                    result['cuda_version'] = '12'
                elif 'cuda_v13' in d:
                    result['cuda_version'] = '13'
        
        logger.info(f"[Hardware] Ollama CUDA libs: {result['cuda_libs_found']} (v{result['cuda_version']})")
        
    except Exception as e:
        logger.error(f"[Hardware] Error checking Ollama CUDA support: {e}")
    
    return result


def check_cpu_info():
    """
    Get CPU information
    """
    result = {
        'cpu_count': 0,
        'cpu_model': None
    }
    
    try:
        # Get CPU count
        cpu_count = subprocess.run(
            ['nproc'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if cpu_count.returncode == 0:
            result['cpu_count'] = int(cpu_count.stdout.strip())
        
        # Get CPU model
        cpu_info = subprocess.run(
            ['lscpu'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if cpu_info.returncode == 0:
            for line in cpu_info.stdout.split('\n'):
                if 'Model name:' in line:
                    result['cpu_model'] = line.split(':', 1)[1].strip()
                    break
        
        logger.info(f"[Hardware] CPU: {result['cpu_model']} ({result['cpu_count']} cores)")
        
    except Exception as e:
        logger.error(f"[Hardware] Error getting CPU info: {e}")
    
    return result


def get_hardware_status():
    """
    Get complete hardware status for AI settings display
    """
    gpu_info = detect_gpu_info()
    cpu_info = check_cpu_info()
    ollama_cuda = check_ollama_cuda_support()
    
    return {
        'gpu': gpu_info,
        'cpu': cpu_info,
        'ollama_cuda': ollama_cuda,
        'recommended_mode': 'gpu' if gpu_info['gpu_detected'] and gpu_info['vram_gb'] >= 8 else 'cpu'
    }


def get_recommended_vram_setting(detected_vram_gb):
    """
    Get recommended VRAM setting based on detected VRAM
    Returns the closest standard VRAM size
    """
    standard_sizes = [4, 6, 8, 12, 16, 24, 32, 40, 48]
    
    if detected_vram_gb <= 0:
        return 8  # Default fallback
    
    # Find closest standard size
    closest = min(standard_sizes, key=lambda x: abs(x - detected_vram_gb))
    return closest


def suggest_models_for_vram(vram_gb):
    """
    Suggest which models will run optimally on given VRAM
    Returns list of model names and their fit status
    """
    # Approximate model sizes (q4_K_M quantization)
    model_sizes = {
        'phi3:3.8b-mini-instruct-4k-q4_K_M': 2.3,
        'gemma2:9b-instruct-q4_K_M': 5.5,
        'qwen2.5:7b-instruct-q4_K_M': 4.7,
        'phi4:14b-q4_K_M': 9.1,
        'qwen2.5:32b-instruct-q4_K_M': 20.0,
        'gemma2:27b-instruct-q4_K_M': 16.5,
        'deepseek-r1:32b-q4_K_M': 21.0,
        'llama3.3:70b-instruct-q4_K_M': 43.0,
        'deepseek-r1:70b-q4_K_M': 45.0
    }
    
    results = {}
    buffer = 1.0  # Leave 1GB buffer for context
    available_vram = vram_gb - buffer
    
    for model_name, model_size in model_sizes.items():
        if model_size <= available_vram:
            results[model_name] = 'optimal'  # Fits entirely in VRAM
        elif model_size <= available_vram + 4:
            results[model_name] = 'hybrid'  # Will use some CPU offloading
        else:
            results[model_name] = 'slow'  # Significant CPU offloading
    
    return results

