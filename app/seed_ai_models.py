#!/usr/bin/env python3
"""
Seed AI Models to Database
Creates ai_model table and populates with 4 DFIR-optimized models
Run: python seed_ai_models.py
"""

from main import app, db
from models import AIModel
import json

def seed_models():
    """Create and seed AI models table"""
    
    with app.app_context():
        # Create table if it doesn't exist
        db.create_all()
        
        # Define the 4 DFIR-optimized models
        models_data = [
            {
                'model_name': 'dfir-llama:latest',
                'display_name': 'DFIR-Llama 3.1 8B (Forensic Profile)',
                'description': 'DFIR-trained forensic analyst profile. Strong evidence discipline, timeline construction, MITRE mapping. No hallucinations. Excellent for general incident response. Runs fully on 7.5GB VRAM.',
                'speed': 'Fast',
                'quality': 'Excellent',
                'size': '4.9 GB',
                'speed_estimate': '~25-35 tok/s GPU (100% on-device), ~10-15 tok/s CPU',
                'time_estimate': '3-5 minutes (GPU), 10-15 minutes (CPU)',
                'recommended': True,
                'trainable': False,  # Llama 3.1 not supported in current Unsloth version
                'base_model': 'unsloth/llama-3.1-8b-instruct-bnb-4bit',
                'cpu_optimal': {'num_ctx': 16384, 'num_thread': 16, 'temperature': 0.3},
                'gpu_optimal': {'num_ctx': 16384, 'num_thread': 8, 'temperature': 0.3, 'num_gpu_layers': -1}
            },
            {
                'model_name': 'dfir-mistral:latest',
                'display_name': 'DFIR-Mistral 7B (Forensic Profile)',
                'description': 'DFIR-trained forensic analyst profile. Efficient chronological reconstruction. Reliable formatting (tables, timelines). Sharp on short-to-mid contexts. Runs fully on 7.5GB VRAM.',
                'speed': 'Fast',
                'quality': 'Excellent',
                'size': '4.4 GB',
                'speed_estimate': '~25-35 tok/s GPU (100% on-device), ~10-15 tok/s CPU',
                'time_estimate': '3-5 minutes (GPU), 10-15 minutes (CPU)',
                'recommended': True,
                'trainable': True,  # Mistral 7B fully supported by Unsloth
                'base_model': 'unsloth/mistral-7b-instruct-v0.3-bnb-4bit',
                'cpu_optimal': {'num_ctx': 16384, 'num_thread': 16, 'temperature': 0.3},
                'gpu_optimal': {'num_ctx': 16384, 'num_thread': 8, 'temperature': 0.3, 'num_gpu_layers': -1}
            },
            {
                'model_name': 'dfir-deepseek:latest',
                'display_name': 'DFIR-DeepSeek-Coder 16B (Forensic Profile)',
                'description': 'DFIR-trained forensic analyst profile specialized in script analysis. PowerShell decoding, obfuscation detection, command-line parsing. Excellent for script-heavy attacks. May use minor CPU offloading (~15%) on 7.5GB VRAM.',
                'speed': 'Moderate',
                'quality': 'Excellent',
                'size': '10 GB',
                'speed_estimate': '~15-25 tok/s GPU (85% on-device, 15% CPU offload), ~8-12 tok/s CPU',
                'time_estimate': '5-8 minutes (GPU), 12-18 minutes (CPU)',
                'recommended': True,
                'trainable': False,  # DeepSeek models not yet supported by Unsloth
                'base_model': 'unsloth/deepseek-coder-v2-lite-instruct-bnb-4bit',
                'cpu_optimal': {'num_ctx': 16384, 'num_thread': 16, 'temperature': 0.3},
                'gpu_optimal': {'num_ctx': 16384, 'num_thread': 16, 'temperature': 0.3, 'num_gpu_layers': -1}
            },
            {
                'model_name': 'dfir-qwen:latest',
                'display_name': 'DFIR-Qwen 2.5 7B (Forensic Profile)',
                'description': 'DFIR-trained forensic analyst profile. Strong structured reasoning. Excellent with long IOC lists (100+) and large event datasets (300+). Constrained reasoning = LOW HALLUCINATION. Runs fully on 7.5GB VRAM.',
                'speed': 'Fast',
                'quality': 'Excellent',
                'size': '4.7 GB',
                'speed_estimate': '~22-32 tok/s GPU (100% on-device), ~9-14 tok/s CPU',
                'time_estimate': '3-5 minutes (GPU), 9-13 minutes (CPU)',
                'recommended': True,
                'trainable': True,  # Qwen 2.5 fully supported by Unsloth
                'base_model': 'unsloth/qwen2-7b-instruct-bnb-4bit',
                'cpu_optimal': {'num_ctx': 16384, 'num_thread': 16, 'temperature': 0.3},
                'gpu_optimal': {'num_ctx': 16384, 'num_thread': 8, 'temperature': 0.3, 'num_gpu_layers': -1}
            }
        ]
        
        # Insert or update models
        for model_data in models_data:
            existing_model = AIModel.query.filter_by(model_name=model_data['model_name']).first()
            
            if existing_model:
                # Update existing model (preserve trained status)
                for key, value in model_data.items():
                    if key not in ['trained', 'trained_date', 'training_examples', 'trained_model_path']:
                        setattr(existing_model, key, value)
                print(f"✅ Updated: {model_data['display_name']}")
            else:
                # Create new model
                model = AIModel(**model_data)
                db.session.add(model)
                print(f"✅ Created: {model_data['display_name']}")
        
        db.session.commit()
        print("\n🎉 AI models seeded successfully!")
        
        # Show summary
        total = AIModel.query.count()
        trainable = AIModel.query.filter_by(trainable=True).count()
        trained = AIModel.query.filter_by(trained=True).count()
        print(f"\n📊 Summary:")
        print(f"   Total models: {total}")
        print(f"   Trainable: {trainable}")
        print(f"   Trained: {trained}")
        print(f"   Not trainable: {total - trainable}")


if __name__ == '__main__':
    seed_models()

