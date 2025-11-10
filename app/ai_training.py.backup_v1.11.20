"""
AI Training Module
Generates training data from OpenCTI threat intelligence
"""

import logging
import json
import os
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


def fetch_opencti_reports(opencti_url, opencti_api_key, limit=100):
    """
    Fetch threat reports from OpenCTI
    
    Args:
        opencti_url: OpenCTI instance URL
        opencti_api_key: API key for authentication
        limit: Maximum number of reports to fetch
    
    Returns:
        list: List of report objects
    """
    logger.info(f"[AI_TRAIN] Fetching up to {limit} reports from OpenCTI...")
    
    try:
        # GraphQL query to fetch reports (minimal fields for speed)
        query = """
        query GetReports($first: Int!) {
            reports(first: $first) {
                edges {
                    node {
                        id
                        name
                        description
                    }
                }
            }
        }
        """
        
        headers = {
            'Authorization': f'Bearer {opencti_api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            f"{opencti_url}/graphql",
            json={'query': query, 'variables': {'first': limit}},
            headers=headers,
            timeout=120  # Increased to 2 minutes for large queries
        )
        
        if response.status_code != 200:
            logger.error(f"[AI_TRAIN] OpenCTI API error: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        
        if 'errors' in data:
            logger.error(f"[AI_TRAIN] OpenCTI GraphQL errors: {data['errors']}")
            return []
        
        reports = []
        for edge in data.get('data', {}).get('reports', {}).get('edges', []):
            node = edge.get('node', {})
            # Only include reports with name and description
            if node.get('name') and node.get('description'):
                reports.append({
                    'id': node.get('id'),
                    'name': node.get('name'),
                    'description': node.get('description')
                })
        
        logger.info(f"[AI_TRAIN] Retrieved {len(reports)} reports from OpenCTI")
        return reports
        
    except Exception as e:
        logger.error(f"[AI_TRAIN] Error fetching OpenCTI reports: {e}", exc_info=True)
        return []


def extract_iocs_from_report(report):
    """
    Extract IOCs from a report (simplified - would need real IOC extraction)
    
    Args:
        report: Report object
    
    Returns:
        list: List of IOC strings
    """
    # Simplified extraction - in production, use proper IOC extraction
    iocs = []
    
    description = report.get('description', '') or ''
    text = description
    
    # Basic pattern matching (very simplified)
    import re
    
    # IPs
    ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    iocs.extend(re.findall(ip_pattern, text))
    
    # Domains (simplified)
    domain_pattern = r'\b[a-z0-9][a-z0-9-]*\.[a-z]{2,}\b'
    iocs.extend(re.findall(domain_pattern, text.lower()))
    
    # File hashes (MD5, SHA1, SHA256)
    hash_pattern = r'\b[a-fA-F0-9]{32,64}\b'
    iocs.extend(re.findall(hash_pattern, text))
    
    return list(set(iocs))[:20]  # Return up to 20 unique IOCs


def extract_mitre_from_report(report):
    """
    Extract MITRE ATT&CK techniques from a report
    
    Args:
        report: Report object
    
    Returns:
        list: List of MITRE technique IDs
    """
    techniques = []
    
    description = report.get('description', '') or ''
    text = description
    
    # Extract MITRE technique IDs (T####)
    import re
    pattern = r'\bT\d{4}(?:\.\d{3})?\b'
    techniques = re.findall(pattern, text)
    
    return list(set(techniques))


def format_training_example(report, iocs, mitre_techniques):
    """
    Format a single training example in JSONL format
    
    Args:
        report: Report object
        iocs: List of IOCs
        mitre_techniques: List of MITRE technique IDs
    
    Returns:
        dict: Training example
    """
    # Construct prompt (input)
    prompt_parts = []
    prompt_parts.append("CASE INFORMATION:")
    prompt_parts.append(f"Case Name: {report.get('name', 'Unknown')}")
    
    # Use full description (not truncated)
    description = report.get('description', 'N/A')
    if description and description != 'N/A':
        prompt_parts.append(f"Threat Intelligence Summary: {description}")
    prompt_parts.append("")
    
    if iocs:
        prompt_parts.append("INDICATORS OF COMPROMISE:")
        for ioc in iocs[:15]:  # Increased from 10 to 15
            prompt_parts.append(f"- {ioc}")
        prompt_parts.append("")
    
    if mitre_techniques:
        prompt_parts.append("OBSERVED TACTICS & TECHNIQUES:")
        for technique in mitre_techniques[:10]:
            prompt_parts.append(f"- {technique}")
        prompt_parts.append("")
    
    prompt = "\n".join(prompt_parts)
    prompt += "\n\nYou are a senior DFIR analyst. Generate a professional incident response report following the DFIR report format with evidence-based timeline, IOC analysis, and MITRE ATT&CK mapping. Use only the data provided."
    
    # Construct response (expected output) - teach DFIR report structure
    response_parts = []
    response_parts.append("# DFIR Investigation Report")
    response_parts.append(f"\n## Case: {report.get('name', 'Unknown')}\n")
    
    response_parts.append("## Executive Summary")
    response_parts.append("")
    
    # Use full description
    description = report.get('description', 'NO DATA PRESENT')
    if description and description != 'NO DATA PRESENT':
        response_parts.append(description)
    else:
        response_parts.append("NO DATA PRESENT")
    
    response_parts.append("")
    response_parts.append("Impact: Based on provided threat intelligence.")
    response_parts.append("")
    
    if iocs:
        response_parts.append("## Indicators of Compromise (IOCs)")
        response_parts.append("")
        response_parts.append("| Indicator | Type | Threat Level | Description |")
        response_parts.append("|-----------|------|--------------|-------------|")
        for ioc in iocs[:15]:
            # Determine IOC type
            if '.' in ioc and len(ioc.split('.')) == 4:
                ioc_type = "IP Address"
            elif len(ioc) == 32:
                ioc_type = "MD5 Hash"
            elif len(ioc) == 40:
                ioc_type = "SHA1 Hash"
            elif len(ioc) == 64:
                ioc_type = "SHA256 Hash"
            else:
                ioc_type = "Domain/Hostname"
            
            response_parts.append(f"| {ioc} | {ioc_type} | High | Observed in threat activity |")
        response_parts.append("")
    
    if mitre_techniques:
        response_parts.append("## MITRE ATT&CK Mapping")
        response_parts.append("")
        for technique in mitre_techniques:
            response_parts.append(f"- **{technique}** | Evidence: Referenced in threat intelligence")
        response_parts.append("")
    elif not mitre_techniques and not iocs:
        # Even without specific IOCs/MITRE, teach proper structure
        response_parts.append("## MITRE ATT&CK Mapping")
        response_parts.append("")
        response_parts.append("MITRE not determinable from provided data")
        response_parts.append("")
    
    response_parts.append("## What Happened")
    response_parts.append("")
    response_parts.append(f"Threat activity identified: {report.get('name', 'Unknown threat')}")
    response_parts.append("")
    
    response_parts.append("## How to Prevent")
    response_parts.append("")
    response_parts.append("- Implement NIST SP 800-53 controls (AC-6, IA-2, AU-2/6/12)")
    response_parts.append("- Deploy EDR/MDR solutions for threat detection")
    response_parts.append("- Enable MFA for all remote access (NIST SP 800-63B)")
    response_parts.append("- Maintain updated threat intelligence feeds")
    response_parts.append("")
    
    response_parts.append("***END OF REPORT***")
    
    response = "\n".join(response_parts)
    
    return {
        'prompt': prompt,
        'response': response
    }


def generate_training_data_from_opencti(opencti_url, opencti_api_key, limit=100, progress_callback=None):
    """
    Generate training data from OpenCTI threat reports
    Fetches in batches of 10 to avoid overwhelming OpenCTI server
    
    Args:
        opencti_url: OpenCTI instance URL
        opencti_api_key: API key
        limit: Total number of reports to fetch (will be fetched in batches of 10)
        progress_callback: Optional callback function for progress updates
    
    Returns:
        dict: {'success': bool, 'file_path': str, 'example_count': int, 'error': str}
    """
    def log(message):
        """Helper to log and call progress callback"""
        logger.info(f"[AI_TRAIN] {message}")
        if progress_callback:
            progress_callback(message)
    
    try:
        import time
        
        # Fetch reports in batches of 10 to avoid overloading OpenCTI
        batch_size = 10
        total_batches = (limit + batch_size - 1) // batch_size  # Ceiling division
        all_reports = []
        
        log(f"Fetching {limit} threat reports from OpenCTI in batches of {batch_size}...")
        log("")
        
        for batch_num in range(total_batches):
            batch_limit = min(batch_size, limit - len(all_reports))
            
            if batch_limit <= 0:
                break
            
            log(f"📦 Batch {batch_num + 1}/{total_batches}: Fetching {batch_limit} reports...")
            
            batch_reports = fetch_opencti_reports(opencti_url, opencti_api_key, batch_limit)
            
            if batch_reports:
                all_reports.extend(batch_reports)
                log(f"   ✅ Retrieved {len(batch_reports)} reports (total: {len(all_reports)})")
            else:
                log(f"   ⚠️  Batch returned 0 reports")
            
            # Small delay between batches to let OpenCTI breathe
            if batch_num < total_batches - 1:
                log(f"   ⏳ Waiting 3 seconds before next batch...")
                time.sleep(3)
        
        log("")
        
        if not all_reports:
            return {
                'success': False,
                'error': 'No reports retrieved from OpenCTI'
            }
        
        log(f"✅ Total reports retrieved: {len(all_reports)}")
        log("")
        log("Extracting IOCs and MITRE techniques...")
        
        reports = all_reports
        
        training_examples = []
        
        for i, report in enumerate(reports):
            if i % 10 == 0:
                log(f"Processing report {i+1}/{len(reports)}...")
            
            # Extract IOCs
            iocs = extract_iocs_from_report(report)
            
            # Extract MITRE techniques
            mitre = extract_mitre_from_report(report)
            
            # Skip reports with no useful data (must have at least name and description)
            if not report.get('name') or not report.get('description'):
                continue
            
            # Generate training example even if no IOCs/MITRE found
            # (the AI can still learn from threat descriptions and report structure)
            example = format_training_example(report, iocs, mitre)
            training_examples.append(example)
        
        log("")
        log(f"✅ Generated {len(training_examples)} training examples")
        log("")
        
        # Save to JSONL file
        output_dir = "/opt/casescope/lora_training/training_data"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{output_dir}/opencti_training_{timestamp}.jsonl"
        
        log(f"Saving training data to: {output_file}")
        
        with open(output_file, 'w') as f:
            for example in training_examples:
                f.write(json.dumps(example) + '\n')
        
        log(f"✅ Training data saved")
        
        return {
            'success': True,
            'file_path': output_file,
            'example_count': len(training_examples)
        }
        
    except Exception as e:
        error_msg = f"Error generating training data: {e}"
        log(f"❌ {error_msg}")
        logger.error(f"[AI_TRAIN] {error_msg}", exc_info=True)
        
        return {
            'success': False,
            'error': str(e)
        }
