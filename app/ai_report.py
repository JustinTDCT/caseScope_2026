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
            
            # Check for phi3:14b specifically
            phi3_available = any('phi3:14b' in name or 'phi3' in name for name in model_names)
            
            return {
                'installed': True,
                'running': True,
                'model_available': phi3_available,
                'models': models,
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


def generate_case_report_prompt(case, iocs, tagged_events, sigma_violations=None, ioc_matches=None):
    """
    Build the prompt for AI report generation following proven DFIR report structure
    
    Args:
        case: Case object
        iocs: List of IOC objects
        tagged_events: List of tagged event dicts from OpenSearch
        sigma_violations: List of (SigmaViolation, SigmaRule) tuples (optional)
        ioc_matches: List of (IOCMatch, IOC) tuples (optional)
        
    Returns:
        str: Formatted prompt for the LLM
    """
    # Build case summary
    prompt = f"""You are a professional DFIR (Digital Forensics and Incident Response) analyst. Generate a comprehensive investigation report following this EXACT 5-part structure:

# CASE: {case.name}
Company: {case.company or 'N/A'}
Status: {case.status}
Investigation Date: {case.created_at.strftime('%Y-%m-%d') if case.created_at else 'N/A'}

Your report MUST have these 5 sections in this order:

## SECTION 1: Executive Summary (3-4 paragraphs)
Write for both technical IR folks and non-technical readers. Include:
- Paragraph 1: What happened (the incident overview)
- Paragraph 2: Why it happened (vulnerabilities exploited, attack vector)
- Paragraph 3: What the actor did (their actions and objectives)
- Paragraph 4: Impact and scope

## SECTION 2: Attack Timeline
Create a chronological timeline from the tagged events below. For each event include:
- Timestamp
- What happened
- MITRE ATT&CK technique (e.g., T1078.001 - Valid Accounts: Domain Accounts)
- Significance

## SECTION 3: Indicators of Compromise (IOCs)
List all IOCs found with their MITRE ATT&CK mappings:
- IP addresses
- Usernames/accounts
- Hostnames
- Commands
- Files/DLLs
- Processes
For each IOC, specify which MITRE technique it relates to.

## SECTION 4: Detailed Technical Analysis
Deep dive into:
- **Initial Access**: How they got in (method, entry point, credentials)
- **Credential Access**: How passwords/credentials were obtained
- **Discovery**: What information they gained (network recon, domain enumeration)
- **Lateral Movement**: How they moved through the network
- **Actions on Objectives**: What they ultimately did

## SECTION 5: Summary & Prevention
Three brief sub-sections:
- **What Happened**: 2-3 sentence summary
- **Why It Happened**: Root cause and security gaps
- **What Could Have Stopped It**: Specific controls (MFA, EDR, network segmentation, etc.)

---

# DATA PROVIDED FOR ANALYSIS:

"""
    
    # Add IOCs
    if iocs:
        prompt += f"\n# Indicators of Compromise ({len(iocs)} IOCs)\n\n"
        
        # Group IOCs by type
        ioc_by_type = {}
        for ioc in iocs:
            ioc_type = ioc.ioc_type or 'unknown'
            if ioc_type not in ioc_by_type:
                ioc_by_type[ioc_type] = []
            ioc_by_type[ioc_type].append(ioc)
        
        for ioc_type, ioc_list in sorted(ioc_by_type.items()):
            prompt += f"\n## {ioc_type.upper()} ({len(ioc_list)} indicators)\n"
            for ioc in ioc_list[:10]:  # Limit to first 10 per type
                flags = []
                if ioc.threat_level:
                    flags.append(ioc.threat_level.upper())
                if not ioc.is_active:
                    flags.append("INACTIVE")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                
                prompt += f"- `{ioc.ioc_value}`{flag_str}"
                if ioc.description:
                    prompt += f" - {ioc.description}"
                prompt += "\n"
            
            if len(ioc_list) > 10:
                prompt += f"... and {len(ioc_list) - 10} more\n"
    
    # Add tagged events
    if tagged_events:
        prompt += f"\n# Tagged Events ({len(tagged_events)} events)\n\n"
        prompt += "Key events flagged by analysts:\n\n"
        
        for i, event in enumerate(tagged_events[:20], 1):  # Limit to first 20 events
            source = event.get('_source', {})
            
            # Extract key fields
            timestamp = source.get('timestamp', source.get('@timestamp', 'Unknown'))
            event_id = source.get('event_id', source.get('EventID', 'N/A'))
            computer = source.get('computer', source.get('Computer', 'N/A'))
            channel = source.get('channel', source.get('Channel', 'N/A'))
            
            prompt += f"### Event {i}\n"
            prompt += f"- **Timestamp**: {timestamp}\n"
            prompt += f"- **Event ID**: {event_id}\n"
            prompt += f"- **Computer**: {computer}\n"
            prompt += f"- **Channel**: {channel}\n"
            
            # Add event data (first 500 chars)
            event_data = source.get('event_data', {})
            if event_data:
                prompt += "- **Event Data**: "
                data_str = json.dumps(event_data, indent=2)[:500]
                prompt += f"```\n{data_str}\n```\n"
            
            prompt += "\n"
        
        if len(tagged_events) > 20:
            prompt += f"... and {len(tagged_events) - 20} more tagged events\n"
    
    # Add instructions - following the proven structure
    prompt += """

---

# **CRITICAL: Follow This EXACT Report Structure**

Generate a professional DFIR investigation report with EXACTLY these 5 sections:

## **SECTION 1: Executive Summary** (3-4 paragraphs)
Write for BOTH technical IR professionals AND non-technical readers:
- **Paragraph 1**: What happened (incident overview, initial detection)
- **Paragraph 2**: Why it happened (vulnerabilities exploited, attack vector, security gaps)
- **Paragraph 3**: What the actor did (their actions, techniques, objectives)
- **Paragraph 4**: Impact and scope (affected systems, data, business impact)

## **SECTION 2: Attack Timeline**
Create a chronological timeline using the tagged events above. For EACH significant event:
- **Timestamp** (exact time)
- **What Happened** (brief description)
- **MITRE ATT&CK Technique** (e.g., T1078.001 - Valid Accounts: Domain Accounts)
- **Significance** (why this event matters)

## **SECTION 3: Indicators of Compromise with MITRE Mapping**
List all IOCs organized by type. For EACH IOC specify:
- The IOC value
- IOC type (IP, Username, Hostname, Command, File, etc.)
- Which MITRE ATT&CK technique(s) it relates to
- Threat level/significance

## **SECTION 4: Detailed Technical Analysis**
Deep dive into the attack mechanics:
- **Initial Access**: Exactly how they got in (method, entry point, credentials used)
- **Credential Access**: How passwords/credentials were obtained (tool, technique, target accounts)
- **Discovery**: What information they gained (network recon, domain enumeration, system discovery)
- **Lateral Movement**: How they moved through the network (RDP, PsExec, WMI, etc.)
- **Actions on Objectives**: What they ultimately did (data access, exfiltration, persistence)

## **SECTION 5: Summary & Prevention**
Three brief but specific sub-sections:
- **What Happened**: 2-3 sentence summary of the entire incident
- **Why It Happened**: Root cause analysis and security gaps that enabled the attack
- **What Could Have Stopped It**: Specific security controls that would have prevented or detected this (e.g., MFA, EDR on all systems, network segmentation, privileged access management, etc.)

---

**IMPORTANT NOTES:**
- Use tagged events as PRIMARY source for timeline
- Map EVERYTHING to MITRE ATT&CK techniques
- Be specific with times, systems, accounts, and actions
- Write professionally but clearly - avoid jargon where possible
- If information is missing, state "Not available in provided data"

Generate the complete report now:
"""
    
    return prompt


def generate_report_with_ollama(prompt, model='phi3:14b', num_ctx=8192, num_thread=12, temperature=0.3):
    """
    Generate report using Ollama API
    
    Args:
        prompt: The prompt to send to the model
        model: Model name (default: phi3:14b)
        num_ctx: Context window size
        num_thread: Number of CPU threads to use
        temperature: Sampling temperature (lower = more focused)
        
    Returns:
        tuple: (success: bool, response: str/dict)
    """
    try:
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'num_ctx': num_ctx,
                'num_thread': num_thread,
                'temperature': temperature,
                'top_p': 0.9,
                'top_k': 40
            }
        }
        
        logger.info(f"[AI] Generating report with {model} (ctx={num_ctx}, threads={num_thread})")
        
        response = requests.post(
            'http://localhost:11434/api/generate',
            json=payload,
            timeout=1800  # 30 minute timeout for CPU inference on 14B model
        )
        
        if response.status_code == 200:
            data = response.json()
            report_text = data.get('response', '')
            
            if not report_text:
                return False, {'error': 'Empty response from model'}
            
            # Extract timing info
            total_duration_ns = data.get('total_duration', 0)
            total_duration_sec = total_duration_ns / 1_000_000_000
            
            logger.info(f"[AI] Report generated successfully in {total_duration_sec:.1f} seconds")
            
            return True, {
                'report': report_text,
                'duration_seconds': total_duration_sec,
                'model': data.get('model', model),
                'eval_count': data.get('eval_count', 0),  # tokens generated
                'prompt_eval_count': data.get('prompt_eval_count', 0)  # tokens in prompt
            }
        else:
            error_msg = f'Ollama API returned status {response.status_code}'
            logger.error(f"[AI] {error_msg}")
            return False, {'error': error_msg, 'response': response.text}
            
    except requests.exceptions.Timeout:
        error_msg = 'Request timed out after 10 minutes'
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


# Export functions
__all__ = [
    'check_ollama_status',
    'generate_case_report_prompt',
    'generate_report_with_ollama',
    'format_report_title'
]

