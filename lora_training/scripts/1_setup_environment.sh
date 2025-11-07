#!/bin/bash
# LoRA Training Environment Setup for CaseScope DFIR
# Optimized for Tesla P4 (8GB VRAM)

set -e

echo "======================================"
echo "  LoRA Training Environment Setup"
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "❌ Please run as casescope user, not root"
   echo "   Usage: sudo -u casescope bash $0"
   exit 1
fi

# Check CUDA availability
echo "🔍 Checking CUDA availability..."
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  nvidia-smi not found. GPU training may not work."
    echo "   Continuing with CPU-only setup (training will be VERY slow)..."
else
    echo "✅ CUDA detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi
echo ""

# Check Python version
echo "🔍 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "   Python version: $PYTHON_VERSION"
if (( $(echo "$PYTHON_VERSION < 3.8" | bc -l) )); then
    echo "❌ Python 3.8+ required (you have $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python version OK"
echo ""

# Create virtual environment for training
echo "📦 Creating Python virtual environment..."
cd /opt/casescope/lora_training
if [ -d "venv" ]; then
    echo "   Virtual environment already exists, skipping..."
else
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate
echo ""

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ pip upgraded"
echo ""

# Install PyTorch with CUDA support (or CPU fallback)
echo "🔥 Installing PyTorch..."
if command -v nvidia-smi &> /dev/null; then
    echo "   Installing with CUDA 12.1 support..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
else
    echo "   Installing CPU-only version (training will be SLOW)..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
fi
echo "✅ PyTorch installed"
echo ""

# Install Unsloth (optimized LoRA training)
echo "🦥 Installing Unsloth (optimized for low VRAM)..."
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
echo "✅ Unsloth installed"
echo ""

# Install training dependencies
echo "📦 Installing training dependencies..."
pip install datasets transformers accelerate peft bitsandbytes trl
echo "✅ Dependencies installed"
echo ""

# Install Ollama Python library (for model export)
echo "📦 Installing Ollama Python library..."
pip install ollama
echo "✅ Ollama library installed"
echo ""

# Create directory structure
echo "📁 Creating directory structure..."
mkdir -p /opt/casescope/lora_training/models
mkdir -p /opt/casescope/lora_training/logs
mkdir -p /opt/casescope/lora_training/training_data
echo "✅ Directories created"
echo ""

# Test PyTorch CUDA
echo "🧪 Testing PyTorch CUDA availability..."
python3 << EOF
import torch
print(f"   PyTorch version: {torch.__version__}")
print(f"   CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   CUDA version: {torch.version.cuda}")
    print(f"   GPU: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    print("   ⚠️  Training will use CPU (VERY slow for 8B models)")
EOF
echo ""

# Save activation script
cat > /opt/casescope/lora_training/activate.sh << 'ACTIVATE_EOF'
#!/bin/bash
# Quick activation script for LoRA training environment
source /opt/casescope/lora_training/venv/bin/activate
echo "✅ LoRA training environment activated"
echo "   Python: $(which python3)"
echo "   To train: python3 scripts/2_train_lora.py --help"
ACTIVATE_EOF
chmod +x /opt/casescope/lora_training/activate.sh

echo ""
echo "======================================"
echo "  ✅ Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Create training examples: nano training_data/examples.jsonl"
echo "2. Activate environment: source activate.sh"
echo "3. Train model: python3 scripts/2_train_lora.py"
echo ""
echo "Example training data format (1 per line):"
echo '{"instruction": "...", "input": "...", "output": "..."}'
echo ""

