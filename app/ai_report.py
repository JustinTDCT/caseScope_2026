#!/usr/bin/env python3
"""
CaseScope AI Report Generation Module
Uses Ollama + Phi-3 Medium 14B for local LLM inference
"""

import requests
import json
from datetime import datetime
from logging_config import get_logger

logger = get_logger('app')


# Model descriptions and metadata
MODEL_INFO = {
    'llama3.1:8b-instruct-q4_K_M': {
        'name': 'LLaMA 3.1 8B (Q4_K_M)',
        'speed': 'Fast',
        'quality': 'Good',
        'size': '4.9 GB',
        'description': 'Balanced speed/quality. Best for CPU. Recommended.',
        'speed_estimate': '~15-18 tok/s CPU, ~40-60 tok/s GPU',
        'time_estimate': '8-12 minutes (CPU), 2-3 minutes (GPU)',
        'recommended': True
    },
    'llama3.1:8b-instruct-q5_K_M': {
        'name': 'LLaMA 3.1 8B (Q5_K_M)',
        'speed': 'Moderate',
        'quality': 'Excellent',
        'size': '5.7 GB',
        'description': 'Higher quality, slower. Better with GPU.',
        'speed_estimate': '~10-12 tok/s CPU, ~35-50 tok/s GPU',
        'time_estimate': '15-20 minutes (CPU), 3-4 minutes (GPU)',
        'recommended': False
    },
    'phi3:14b': {
        'name': 'Phi-3 Medium 14B (Q4_0)',
        'speed': 'Very Slow',
        'quality': 'Excellent',
        'size': '7.9 GB',
        'description': 'Highest quality, very slow on CPU. GPU recommended.',
        'speed_estimate': '~5-8 tok/s CPU, ~20-30 tok/s GPU',
        'time_estimate': '30+ minutes (CPU), 5-7 minutes (GPU)',
        'recommended': False
    },
    'phi3:14b-medium-4k-instruct-q4_K_M': {
        'name': 'Phi-3 Medium 14B (Q4_K_M)',
        'speed': 'Slow',
        'quality': 'Excellent',
        'size': '8.6 GB',
        'description': 'High quality, slow on CPU. GPU recommended.',
        'speed_estimate': '~6-9 tok/s CPU, ~25-35 tok/s GPU',
        'time_estimate': '25-30 minutes (CPU), 4-6 minutes (GPU)',
        'recommended': False
    },
    'mixtral:8x7b-instruct-v0.1-q4_K_M': {
        'name': 'Mixtral 8x7B Instruct (Q4_K_M)',
        'speed': 'Moderate',
        'quality': 'Excellent',
        'size': '26 GB',
        'description': 'Mixture-of-Experts model. Superior reasoning and instruction following. 32K context window.',
        'speed_estimate': '~3-5 tok/s CPU, ~15-25 tok/s GPU',
        'time_estimate': '10-15 minutes (CPU), 3-5 minutes (GPU)',
        'recommended': False
    },
    'mixtral:8x7b-instruct-v0.1-q3_K_M': {
        'name': 'Mixtral 8x7B Instruct (Q3_K_M)',
        'speed': 'Fast',
        'quality': 'Very Good',
        'size': '20 GB',
        'description': 'Faster Mixtral variant. Good balance of speed and quality. 32K context window.',
        'speed_estimate': '~5-8 tok/s CPU, ~20-30 tok/s GPU',
        'time_estimate': '8-12 minutes (CPU), 2-4 minutes (GPU)',
        'recommended': False
    },
    'mixtral-longform': {
        'name': 'Mixtral 8x7B Longform (Custom)',
        'speed': 'Moderate',
        'quality': 'Excellent',
        'size': '26 GB',
        'description': 'Custom Mixtral model optimized for long-form report generation. Has num_predict=4096 built-in.',
        'speed_estimate': '~3-5 tok/s CPU, ~15-25 tok/s GPU',
        'time_estimate': '10-15 minutes (CPU), 3-5 minutes (GPU)',
        'recommended': False
    },
    'qwen2.5:72b': {
        'name': 'Qwen 2.5 72B (Q4_K_M)',
        'speed': 'Slow',
        'quality': 'Outstanding',
        'size': '47 GB',
        'description': 'Best open-source instruction follower. Extremely low hallucination rate. 128K context. RECOMMENDED for accuracy.',
        'speed_estimate': '~2-4 tok/s CPU, ~10-20 tok/s GPU',
        'time_estimate': '15-25 minutes (CPU), 4-8 minutes (GPU)',
        'recommended': True
    },
    'qwen2.5:32b': {
        'name': 'Qwen 2.5 32B (Q4_K_M)',
        'speed': 'Moderate',
        'quality': 'Excellent',
        'size': '20 GB',
        'description': 'Balanced Qwen model. Better instruction following than Mixtral. 128K context.',
        'speed_estimate': '~4-6 tok/s CPU, ~18-28 tok/s GPU',
        'time_estimate': '8-15 minutes (CPU), 3-5 minutes (GPU)',
        'recommended': False
    },
    'qwen2.5:14b': {
        'name': 'Qwen 2.5 14B (Q4_K_M)',
        'speed': 'Fast',
        'quality': 'Very Good',
        'size': '9 GB',
        'description': 'Faster Qwen model. Good for quick reports. 128K context.',
        'speed_estimate': '~7-10 tok/s CPU, ~25-35 tok/s GPU',
        'time_estimate': '5-10 minutes (CPU), 2-4 minutes (GPU)',
        'recommended': False
    }
}


def get_model_info(model_name):
    """Get metadata for a specific model"""
    return MODEL_INFO.get(model_name, {
        'name': model_name,
        'speed': 'Unknown',
        'quality': 'Unknown',
        'size': 'Unknown',
        'description': 'Custom model',
        'speed_estimate': 'Unknown',
        'time_estimate': 'Unknown',
        'recommended': False
    })


def check_ollama_status():
    """
    Check if Ollama is running and Phi-3 model is available
    
    Returns:
        dict: Status information
            {
                'installed': bool,
                'running': bool,
                'model_available': bool,
                'models': list,
                'error': str (if any)
            }
    """
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            model_names = [m.get('name', '') for m in models]
            
            # Enrich models with metadata
            enriched_models = []
            for model in models:
                model_name = model.get('name', '')
                info = get_model_info(model_name)
                enriched_models.append({
                    'name': model_name,
                    'display_name': info['name'],
                    'speed': info['speed'],
                    'quality': info['quality'],
                    'size': info['size'],
                    'description': info['description'],
                    'speed_estimate': info['speed_estimate'],
                    'time_estimate': info['time_estimate'],
                    'recommended': info['recommended'],
                    'size_bytes': model.get('size', 0),
                    'modified_at': model.get('modified_at', '')
                })
            
            # Check for any AI model
            model_available = len(models) > 0
            
            return {
                'installed': True,
                'running': True,
                'model_available': model_available,
                'models': enriched_models,
                'model_names': model_names,
                'error': None
            }
        else:
            return {
                'installed': False,
                'running': False,
                'model_available': False,
                'models': [],
                'model_names': [],
                'error': f'Ollama returned status code {response.status_code}'
            }
    except requests.exceptions.ConnectionError:
        return {
            'installed': False,
            'running': False,
            'model_available': False,
            'models': [],
            'model_names': [],
            'error': 'Cannot connect to Ollama (not installed or not running)'
        }
    except Exception as e:
        logger.error(f"[AI] Error checking Ollama status: {e}")
        return {
            'installed': False,
            'running': False,
            'model_available': False,
            'models': [],
            'model_names': [],
            'error': str(e)
        }


def generate_case_report_prompt(case, iocs, tagged_events):
    """
    Build the prompt for AI report generation using HARD RESET structure to prevent hallucination
    
    Args:
        case: Case object
        iocs: List of IOC objects
        tagged_events: List of tagged event dicts from OpenSearch
        
    Returns:
        str: Formatted prompt for the LLM with strict data boundaries
    """
    
    # Build the prompt with HARD RESET CONTEXT structure
    prompt = f"""HARD RESET CONTEXT.

YOU MUST FOLLOW THESE RULES — NO EXCEPTIONS:

1. ONLY use the data between <<<DATA>>> and <<<END DATA>>>.

2. If a detail is not in the dataset, write "NO DATA PRESENT".

3. Produce ALL sections before stopping:
   A. Executive Summary (3–5 paragraphs)
   B. Timeline (every event in chronological order, earliest first)
   C. IOCs (table format with all IOCs listed)
   D. MITRE Mapping
   E. What Happened / Why / How to Prevent

4. Minimum output length = 1200 words.

5. Do NOT summarize. Do NOT infer. Do NOT make up ANY details.

6. When finished, output exactly: ***END OF REPORT***

7. If output reaches token limit, CONTINUE WRITING without waiting for user.

8. Use term "destination systems" NOT "target systems".

9. IPs listed are SSLVPN assigned IPs (not public internet IPs).

10. All timestamps are in UTC format.

---

<<<DATA>>>

CASE INFORMATION:
Case Name: {case.name}
Company: {case.company or 'N/A'}
Investigation Date: {case.created_at.strftime('%Y-%m-%d') if case.created_at else 'N/A'}

"""
    
    # Add IOCs in simple CSV-like format
    if iocs:
        prompt += f"INDICATORS OF COMPROMISE ({len(iocs)} total):\n"
        for ioc in iocs:
            prompt += f"- IOC: {ioc.ioc_value} | Type: {ioc.ioc_type or 'unknown'}"
            if ioc.threat_level:
                prompt += f" | Threat Level: {ioc.threat_level}"
            if ioc.description:
                prompt += f" | Description: {ioc.description}"
            prompt += "\n"
        prompt += "\n"
    else:
        prompt += "INDICATORS OF COMPROMISE: None defined\n\n"
    
    # Add tagged events in simple format (CSV-like)
    if tagged_events:
        prompt += f"TAGGED EVENTS ({len(tagged_events)} events):\n\n"
        
        for i, event in enumerate(tagged_events, 1):
            source = event.get('_source', {})
            
            # Get core fields
            timestamp = source.get('timestamp', source.get('@timestamp', 'Unknown'))
            event_id = source.get('event_id', source.get('EventID', 'N/A'))
            computer = source.get('computer_name', source.get('computer', source.get('Computer', 'N/A')))
            description = source.get('description', 'No description')
            
            prompt += f"Event {i}:\n"
            prompt += f"  Timestamp: {timestamp}\n"
            prompt += f"  Event ID: {event_id}\n"
            prompt += f"  Computer: {computer}\n"
            prompt += f"  Description: {description}\n"
            
            # Add ALL other fields (don't filter - give AI all data)
            exclude_fields = {'timestamp', '@timestamp', 'event_id', 'EventID', 'computer_name', 'computer', 
                            'Computer', 'description', 'source_type', 'source_file', 'has_sigma', 'has_ioc',
                            '@version', '_index', '_type', '_score', 'tags'}
            
            for key, value in source.items():
                if key not in exclude_fields and value and str(value).strip():
                    prompt += f"  {key}: {value}\n"
            
            prompt += "\n"
    else:
        prompt += "TAGGED EVENTS: None available\n\n"
    
    # Close the data section
    prompt += """
<<<END DATA>>>

Generate a professional DFIR investigation report with ALL sections (A through E) listed in the rules above.

Use markdown formatting. Be thorough and detailed. Minimum 1200 words.

Begin now.
"""
    
    return prompt


def generate_report_with_ollama(prompt, model='llama3.1:8b-instruct-q5_K_M', num_ctx=4096, num_thread=16, temperature=0.3, report_obj=None, db_session=None):
    """
    Generate report using Ollama API with real-time streaming
    
    Args:
        prompt: The prompt to send to the model
        model: Model name (default: llama3.1:8b-instruct-q5_K_M)
        num_ctx: Context window size (4096 for faster generation)
        num_thread: Number of CPU threads to use (16 to match system cores)
        temperature: Sampling temperature (lower = more focused)
        report_obj: AIReport database object for real-time updates (optional)
        db_session: Database session for committing updates (optional)
        
    Returns:
        tuple: (success: bool, response: str/dict)
    """
    import time
    
    try:
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': True,  # Enable streaming for real-time updates
            'options': {
                'num_ctx': num_ctx,
                'num_thread': num_thread,
                'num_predict': 8192,  # VERY HIGH: Force maximum output length (was 4096, still truncating)
                'temperature': temperature,
                'top_p': 0.9,
                'top_k': 40,
                'stop': []  # CRITICAL: Remove ALL stop sequences that might be terminating early
            }
        }
        
        logger.info(f"[AI] Generating report with {model} (ctx={num_ctx}, threads={num_thread}, STREAMING=ON)")
        
        response = requests.post(
            'http://localhost:11434/api/generate',
            json=payload,
            stream=True,  # Enable response streaming
            timeout=2400  # 40 minute timeout (Qwen 2.5 72B needs 20-25 minutes)
        )
        
        if response.status_code == 200:
            report_text = ''
            tokens_generated = 0
            start_time = time.time()
            last_update_time = start_time
            last_update_tokens = 0
            prompt_eval_count = 0
            total_duration = 0
            
            # Process streaming response
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        
                        # Append response text
                        if 'response' in chunk:
                            report_text += chunk['response']
                            tokens_generated += 1
                        
                        # Get prompt eval count (only in first chunk)
                        if 'prompt_eval_count' in chunk and prompt_eval_count == 0:
                            prompt_eval_count = chunk.get('prompt_eval_count', 0)
                        
                        # Update database every 50 tokens (real-time feedback)
                        current_time = time.time()
                        if report_obj and db_session and tokens_generated > 0:
                            if tokens_generated % 50 == 0 or (current_time - last_update_time) >= 5:
                                elapsed = current_time - start_time
                                if elapsed > 0:
                                    current_tps = tokens_generated / elapsed
                                    
                                    # Update report with real-time metrics
                                    report_obj.total_tokens = tokens_generated
                                    report_obj.tokens_per_second = current_tps
                                    report_obj.progress_message = f'Generating report... {tokens_generated} tokens at {current_tps:.1f} tok/s'
                                    
                                    try:
                                        db_session.commit()
                                        logger.info(f"[AI] Progress: {tokens_generated} tokens, {current_tps:.2f} tok/s")
                                    except Exception as e:
                                        logger.warning(f"[AI] Failed to update progress: {e}")
                                        db_session.rollback()
                                    
                                    last_update_time = current_time
                                    last_update_tokens = tokens_generated
                        
                        # Check if this is the final chunk
                        if chunk.get('done', False):
                            total_duration = chunk.get('total_duration', 0) / 1_000_000_000
                            eval_count = chunk.get('eval_count', tokens_generated)
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"[AI] Failed to parse chunk: {e}")
                        continue
            
            # Final calculations
            generation_time = time.time() - start_time
            
            if not report_text:
                return False, {'error': 'Empty response from model'}
            
            # Calculate final tokens/second
            if generation_time > 0 and tokens_generated > 0:
                final_tps = tokens_generated / generation_time
                logger.info(f"[AI] Report generated in {generation_time:.1f}s | {tokens_generated} tokens | {final_tps:.2f} tok/s")
            else:
                final_tps = 0
                logger.info(f"[AI] Report generated in {generation_time:.1f} seconds")
            
            return True, {
                'report': report_text,
                'duration_seconds': generation_time,
                'model': model,
                'eval_count': tokens_generated,
                'prompt_eval_count': prompt_eval_count
            }
        else:
            error_msg = f'Ollama API returned status {response.status_code}'
            logger.error(f"[AI] {error_msg}")
            return False, {'error': error_msg, 'response': response.text}
            
    except requests.exceptions.Timeout:
        error_msg = 'Request timed out after 20 minutes (may need GPU acceleration or host CPU optimization)'
        logger.error(f"[AI] {error_msg}")
        return False, {'error': error_msg}
    except Exception as e:
        error_msg = f'Error generating report: {str(e)}'
        logger.error(f"[AI] {error_msg}")
        return False, {'error': error_msg}


def format_report_title(case_name):
    """Generate a title for the AI report"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    return f"DFIR Investigation Report: {case_name} - {timestamp}"


def markdown_to_html(markdown_text, case_name, company_name=""):
    """
    Convert markdown report to professional HTML suitable for Microsoft Word
    
    Args:
        markdown_text: The markdown-formatted report
        case_name: Name of the case
        company_name: Company name (optional)
        
    Returns:
        str: HTML document with professional formatting
    """
    import re
    from datetime import datetime
    
    # Process line by line to preserve structure
    html = markdown_text
    
    # Headers (### to h3, ## to h2, # to h1) - do first before other conversions
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Bold and code formatting
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'`(.*?)`', r'<code>\1</code>', html)
    
    # Convert bullet lists - handle nested indentation
    # First convert double-indented bullets (sub-items with 2+ spaces)
    html = re.sub(r'^  - (.*?)$', r'<li class="indent2">\1</li>', html, flags=re.MULTILINE)
    # Then convert single-level bullets
    html = re.sub(r'^- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    
    # Wrap consecutive <li> items in <ul> - handle both regular and indented
    def wrap_list_items(match):
        content = match.group(0)
        # Check if this is an indented list
        if '<li class="indent2">' in content:
            return '<ul class="nested">\n' + content + '</ul>\n'
        return '<ul>\n' + content + '</ul>\n'
    
    # Wrap list items that are grouped together
    html = re.sub(r'(?:<li[^>]*>.*?</li>\n)+', wrap_list_items, html, flags=re.DOTALL)
    
    # Handle paragraphs - but don't wrap headers or lists
    lines = html.split('\n')
    processed_lines = []
    in_paragraph = False
    
    for line in lines:
        stripped = line.strip()
        # Skip empty lines, headers, and list items
        if not stripped or stripped.startswith('<h') or stripped.startswith('<ul') or stripped.startswith('</ul') or stripped.startswith('<li'):
            if in_paragraph:
                processed_lines.append('</p>')
                in_paragraph = False
            processed_lines.append(line)
        else:
            if not in_paragraph:
                processed_lines.append('<p>')
                in_paragraph = True
            processed_lines.append(line + '<br/>')
    
    if in_paragraph:
        processed_lines.append('</p>')
    
    html = '\n'.join(processed_lines)
    
    # Create full HTML document with professional styling
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    company_line = f"<p><strong>Company:</strong> {company_name}</p>" if company_name else ""
    
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DFIR Investigation Report - {case_name}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 1in;
            color: #333;
            background: white;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            font-size: 28pt;
        }}
        h2 {{
            color: #2980b9;
            border-bottom: 2px solid #bdc3c7;
            padding-bottom: 8px;
            margin-top: 30px;
            font-size: 20pt;
        }}
        h3 {{
            color: #34495e;
            margin-top: 20px;
            font-size: 16pt;
        }}
        h4 {{
            color: #7f8c8d;
            margin-top: 15px;
            font-size: 14pt;
        }}
        p {{
            margin: 10px 0;
            text-align: justify;
        }}
        code {{
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 9pt;
        }}
        strong {{
            color: #c0392b;
            font-weight: bold;
        }}
        ul {{
            margin: 10px 0;
            padding-left: 30px;
            list-style-type: disc;
        }}
        ul.nested {{
            margin: 5px 0;
            padding-left: 40px;
            list-style-type: circle;
        }}
        li {{
            margin: 5px 0;
            line-height: 1.4;
        }}
        li.indent2 {{
            margin-left: 20px;
        }}
        .header {{
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            border: none;
        }}
        .metadata {{
            color: #7f8c8d;
            font-size: 10pt;
        }}
        @media print {{
            body {{
                margin: 0;
                padding: 0.5in;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DFIR Investigation Report</h1>
        <p class="metadata"><strong>Case:</strong> {case_name}</p>
        {company_line}
        <p class="metadata"><strong>Generated:</strong> {timestamp}</p>
    </div>
    
    {html}
    
    <hr style="margin-top: 40px; border: none; border-top: 2px solid #bdc3c7;">
    <p class="metadata" style="text-align: center; font-size: 9pt;">
        Report generated by CaseScope DFIR Platform
    </p>
</body>
</html>"""
    
    return full_html


def refine_report_with_chat(user_request, current_report, case, iocs, tagged_events, chat_history=None, model='llama3.1:8b-instruct-q4_K_M'):
    """
    Refine an existing report based on user's chat request
    
    Args:
        user_request (str): User's refinement request
        current_report (str): The current HTML report content
        case: Case object
        iocs: List of IOC objects
        tagged_events: List of tagged event dictionaries
        chat_history (list): Previous chat messages [{'role': 'user'|'assistant', 'message': '...'}]
        model (str): Ollama model to use
    
    Returns:
        Generator yielding chat response chunks
    """
    from bs4 import BeautifulSoup
    
    # Convert HTML report back to text for context
    soup = BeautifulSoup(current_report, 'html.parser')
    report_text = soup.get_text()
    
    # Build context-aware prompt
    prompt = f"""You are a DFIR report refinement assistant. A security analyst is reviewing a DFIR report and wants to make changes.

**YOUR TASK**: Respond to the analyst's request by providing ONLY the refined/new content they asked for.

**CRITICAL RULES**:
1. ⚠️ **USE ONLY DATA PROVIDED** - Do NOT invent, assume, or fabricate ANY details
2. ⚠️ **RESPOND DIRECTLY** - Provide the actual content they requested, not explanations about what you'll do
3. ⚠️ **MATCH EXISTING FORMAT** - Use the same HTML formatting style as the current report
4. ⚠️ **BE SPECIFIC** - Reference exact timestamps, IPs, hostnames, usernames from the events
5. ⚠️ **STAY FOCUSED** - Only address what they asked for, don't rewrite the entire report

**CURRENT REPORT EXCERPT** (first 2000 chars for context):
```
{report_text[:2000]}
```

**AVAILABLE CASE DATA**:
"""
    
    # Add event summary
    if tagged_events:
        prompt += f"\n**Tagged Events**: {len(tagged_events)} events available\n"
        prompt += "**Sample Event Data** (first 3 events):\n"
        for i, evt in enumerate(tagged_events[:3]):
            evt_data = evt.get('_source', {})
            timestamp = evt_data.get('@timestamp', evt_data.get('timestamp', 'N/A'))
            computer = evt_data.get('Computer', evt_data.get('computer', evt_data.get('host', {}).get('name', 'N/A')))
            prompt += f"\n{i+1}. Time: {timestamp}, System: {computer}\n"
            # Add key fields
            for key in ['Event_ID', 'event_id', 'Target_User_Name', 'target_user', 'Source_Network_Address', 'source_ip', 'CommandLine', 'command_line']:
                if key in evt_data and evt_data[key]:
                    prompt += f"   - {key}: {evt_data[key]}\n"
    
    # Add IOC summary
    if iocs:
        prompt += f"\n**IOCs**: {len(iocs)} indicators available\n"
        for ioc in iocs[:5]:
            prompt += f"- {ioc.ioc_value} ({ioc.ioc_type})\n"
    
    # Add chat history for context
    if chat_history:
        prompt += "\n**PREVIOUS CONVERSATION**:\n"
        for msg in chat_history[-5:]:  # Last 5 messages for context
            role_label = "Analyst" if msg['role'] == 'user' else "You"
            prompt += f"{role_label}: {msg['message']}\n"
    
    # Add current user request
    prompt += f"\n**ANALYST'S REQUEST**:\n{user_request}\n\n"
    
    prompt += """
**YOUR RESPONSE**:
Provide ONLY the refined content requested. Format it in HTML suitable for the report.
If they asked to:
- "Add more detail" → Provide the expanded section with the additional details
- "Rewrite for executives" → Provide the rewritten text in simpler language
- "Expand timeline" → Provide additional timeline entries in the same format
- "Add a section" → Provide the complete new section with proper HTML headers

DO NOT:
- Say "I'll do this" or "Here's how I'll change it"
- Provide explanations of what you're doing
- Repeat their request back to them
- Offer to do it - JUST DO IT and provide the content

BEGIN YOUR RESPONSE:
"""
    
    # Call Ollama with streaming
    ollama_url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,  # Lower temperature for more focused refinements
            "num_ctx": 8192,  # Larger context for full report
            "num_thread": 16
        }
    }
    
    try:
        response = requests.post(ollama_url, json=payload, stream=True, timeout=300)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line.decode('utf-8'))
                    if 'response' in chunk:
                        yield chunk['response']
                    if chunk.get('done', False):
                        break
                except json.JSONDecodeError:
                    continue
                    
    except Exception as e:
        logger.error(f"[AI Chat] Error during refinement: {str(e)}")
        yield f"\n\n❌ Error: {str(e)}"


# Export functions
__all__ = [
    'check_ollama_status',
    'generate_case_report_prompt',
    'generate_report_with_ollama',
    'format_report_title',
    'markdown_to_html',
    'refine_report_with_chat'
]

