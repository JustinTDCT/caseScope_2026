"""
AI Model Training Module
Handles LoRA training using OpenCTI threat intelligence
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_opencti_reports(opencti_url, opencti_api_key, limit=100):
    """
    Fetch threat reports from OpenCTI
    
    Returns:
        List of reports with IOCs, MITRE techniques, and descriptions
    """
    from opencti_integration import get_opencti_client
    
    try:
        logger.info(f"[AI Training] Connecting to OpenCTI: {opencti_url}")
        client = get_opencti_client(opencti_url, opencti_api_key)
        
        if not client:
            raise Exception("Failed to connect to OpenCTI")
        
        logger.info(f"[AI Training] Fetching up to {limit} threat reports...")
        
        # Query reports using OpenCTI API
        query = """
            query GetReports($first: Int!) {
                reports(first: $first, orderBy: published, orderMode: desc) {
                    edges {
                        node {
                            id
                            name
                            description
                            published
                            report_types
                            objectMarking {
                                edges {
                                    node {
                                        definition
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """
        
        result = client.query(query, {'first': limit})
        
        if not result or 'data' not in result:
            raise Exception("Invalid response from OpenCTI")
        
        reports = []
        for edge in result['data']['reports']['edges']:
            node = edge['node']
            reports.append({
                'id': node['id'],
                'name': node['name'],
                'description': node['description'],
                'published': node['published'],
                'report_types': node.get('report_types', [])
            })
        
        logger.info(f"[AI Training] Fetched {len(reports)} reports from OpenCTI")
        return reports
        
    except Exception as e:
        logger.error(f"[AI Training] Error fetching OpenCTI reports: {e}")
        raise


def extract_iocs_from_report(opencti_client, report_id):
    """Extract IOCs linked to a specific report"""
    try:
        # Query for observables linked to this report
        query = """
            query GetReportObservables($reportId: String!) {
                report(id: $reportId) {
                    observables {
                        edges {
                            node {
                                entity_type
                                observable_value
                            }
                        }
                    }
                }
            }
        """
        
        result = opencti_client.query(query, {'reportId': report_id})
        
        iocs = []
        if result and 'data' in result and result['data'].get('report'):
            for edge in result['data']['report'].get('observables', {}).get('edges', []):
                node = edge['node']
                iocs.append({
                    'type': node['entity_type'],
                    'value': node['observable_value']
                })
        
        return iocs
        
    except Exception as e:
        logger.warning(f"[AI Training] Error extracting IOCs from report {report_id}: {e}")
        return []


def extract_mitre_from_report(opencti_client, report_id):
    """Extract MITRE ATT&CK techniques linked to a report"""
    try:
        query = """
            query GetReportAttackPatterns($reportId: String!) {
                report(id: $reportId) {
                    attackPatterns {
                        edges {
                            node {
                                name
                                x_mitre_id
                                description
                            }
                        }
                    }
                }
            }
        """
        
        result = opencti_client.query(query, {'reportId': report_id})
        
        techniques = []
        if result and 'data' in result and result['data'].get('report'):
            for edge in result['data']['report'].get('attackPatterns', {}).get('edges', []):
                node = edge['node']
                techniques.append({
                    'id': node.get('x_mitre_id', 'Unknown'),
                    'name': node['name'],
                    'description': node.get('description', '')
                })
        
        return techniques
        
    except Exception as e:
        logger.warning(f"[AI Training] Error extracting MITRE from report {report_id}: {e}")
        return []


def format_training_example(report, iocs, mitre_techniques):
    """
    Format OpenCTI report data into a training example
    
    Returns:
        Dictionary with instruction, input, and output template
    """
    # Format INPUT (case data)
    input_text = f"CASE: {report['name']}\n\n"
    input_text += f"SOURCE: OpenCTI Threat Intelligence\n"
    input_text += f"DATE: {report.get('published', 'Unknown')}\n\n"
    
    if iocs:
        input_text += "IOCs:\n"
        for ioc in iocs[:20]:  # Limit to 20 IOCs
            input_text += f"- {ioc['value']} ({ioc['type']})\n"
        input_text += "\n"
    
    if mitre_techniques:
        input_text += "MITRE ATT&CK Techniques:\n"
        for tech in mitre_techniques[:15]:  # Limit to 15 techniques
            input_text += f"- {tech['id']}: {tech['name']}\n"
        input_text += "\n"
    
    input_text += "DESCRIPTION:\n"
    input_text += (report.get('description', 'No description available')[:1000] + "\n\n")  # Limit description
    
    input_text += "SYSTEMS:\n"
    input_text += "[Extract from case or events - to be filled during training]\n\n"
    
    input_text += "EVENTS:\n"
    input_text += "[Add specific events with timestamps - to be filled during training]\n"
    
    # FORMAT OUTPUT (industry-standard DFIR report structure)
    output_template = generate_dfir_report_template(report['name'], iocs, mitre_techniques)
    
    return {
        'instruction': "Generate a DFIR investigation report with timeline, MITRE mapping, executive summary, and remediation recommendations. Use only the evidence provided.",
        'input': input_text,
        'output': output_template,
        'metadata': {
            'source': 'OpenCTI',
            'report_id': report['id'],
            'report_name': report['name'],
            'ioc_count': len(iocs),
            'mitre_count': len(mitre_techniques)
        }
    }


def generate_dfir_report_template(case_name, iocs, mitre_techniques):
    """Generate industry-standard DFIR report template based on OpenCTI data"""
    
    report = f"""# DFIR Investigation Report

## Executive Summary

[Based on the threat intelligence from OpenCTI regarding {case_name}, provide a 3-paragraph executive summary covering: 1) What happened (attack vector, initial access), 2) The sequence of events and attacker progression, 3) Observed impact and affected systems. Use only data present in the case.]

[Paragraph 2: Detail the tactics, techniques, and procedures (TTPs) observed, referencing specific MITRE ATT&CK techniques where applicable. Describe the attacker's objectives and methods.]

[Paragraph 3: Summarize the impact. If impact is unclear from provided data, state "Impact: NO DATA PRESENT".]

## Timeline

[Timestamp or NO DATA PRESENT] — [Action observed]
System: [System name or NO DATA PRESENT]
User/Account: [Username or NO DATA PRESENT]
IOC: [IOC value from list or NO DATA PRESENT]
Evidence: [Event ID/source + brief quoted field from data]
MITRE: [TACTIC / T#### Technique Name or "MITRE not determinable from provided data"]

[Continue with additional timeline entries in strict chronological order, earliest first]

## IOCs

| Indicator | Type | Threat Level | Description | First Seen | Systems/Events |
|-----------|------|--------------|-------------|------------|----------------|
"""
    
    # Add IOCs from OpenCTI
    for ioc in iocs[:10]:  # Top 10 IOCs
        report += f"| {ioc['value']} | {ioc['type']} | [Assess based on context] | [Describe role in attack] | [Timestamp or NO DATA PRESENT] | [Systems or NO DATA PRESENT] |\n"
    
    report += "\n## MITRE Mapping\n\n"
    
    # Add MITRE techniques from OpenCTI
    for tech in mitre_techniques[:10]:  # Top 10 techniques
        report += f"**[TACTIC]** — {tech['id']} {tech['name']} | Evidence: [timestamps/records or NO DATA PRESENT]\n\n"
    
    report += """## What Happened

[1 paragraph: Plain English description of the attack sequence, based only on provided data]

## Why It Happened

[Identify control gaps only if evidenced in the data. If not evidenced, state "NO DATA PRESENT". Examples: missing MFA, weak credentials, lack of monitoring, insufficient network segmentation]

## How to Prevent

[Provide specific, actionable recommendations aligned with NIST frameworks:]

1. **[Control Name]** (NIST SP 800-53 [Control ID]): [Specific recommendation based on observed gaps]

2. **Multi-Factor Authentication** (NIST SP 800-63B § 4.2): Implement/verify MFA for all administrative accounts and VPN access.

3. **Enhanced Monitoring** (NIST SP 800-53 AU-2, AU-6): Implement/verify logging and alerting for [specific events observed in this attack].

4. **Network Segmentation** (NIST SP 800-53 SC-7): Implement/verify network controls to prevent [specific lateral movement observed].

5. **Incident Response Plan** (NIST SP 800-61): Implement/verify IR procedures for detecting and responding to [attack type].

***END OF REPORT***
"""
    
    return report


def save_training_examples(examples, output_file="/opt/casescope/lora_training/training_data/opencti_examples.jsonl"):
    """Save training examples to JSONL file"""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        for example in examples:
            # Remove metadata before saving (keep only instruction, input, output)
            training_example = {
                'instruction': example['instruction'],
                'input': example['input'],
                'output': example['output']
            }
            f.write(json.dumps(training_example, ensure_ascii=False) + '\n')
    
    logger.info(f"[AI Training] Saved {len(examples)} training examples to {output_path}")
    return str(output_path)


def generate_training_data_from_opencti(opencti_url, opencti_api_key, limit=100, progress_callback=None):
    """
    Main function to generate training data from OpenCTI
    
    Args:
        opencti_url: OpenCTI instance URL
        opencti_api_key: OpenCTI API key
        limit: Maximum number of reports to fetch
        progress_callback: Optional callback function for progress updates
    
    Returns:
        Dictionary with success status, file path, and statistics
    """
    def log(message):
        logger.info(f"[AI Training] {message}")
        if progress_callback:
            progress_callback(message)
    
    try:
        log("Starting training data generation from OpenCTI")
        
        # Fetch reports
        log(f"Fetching up to {limit} threat reports from OpenCTI...")
        reports = fetch_opencti_reports(opencti_url, opencti_api_key, limit)
        log(f"✅ Fetched {len(reports)} reports")
        
        if len(reports) < 10:
            raise Exception(f"Insufficient reports (need at least 10, got {len(reports)})")
        
        # Get OpenCTI client for detailed queries
        from opencti_integration import get_opencti_client
        client = get_opencti_client(opencti_url, opencti_api_key)
        
        # Process each report
        examples = []
        log(f"Processing reports and extracting IOCs/MITRE techniques...")
        
        for idx, report in enumerate(reports, 1):
            try:
                log(f"Processing report {idx}/{len(reports)}: {report['name'][:50]}...")
                
                # Extract IOCs and MITRE techniques
                iocs = extract_iocs_from_report(client, report['id'])
                mitre_techniques = extract_mitre_from_report(client, report['id'])
                
                # Format as training example
                example = format_training_example(report, iocs, mitre_techniques)
                examples.append(example)
                
                if idx % 10 == 0:
                    log(f"Processed {idx}/{len(reports)} reports...")
                
            except Exception as e:
                log(f"⚠️  Error processing report {idx}: {e}")
                continue
        
        log(f"✅ Processed {len(examples)} training examples")
        
        if len(examples) < 10:
            raise Exception(f"Insufficient training examples (need at least 10, got {len(examples)})")
        
        # Save to file
        log("Saving training examples to JSONL file...")
        output_file = save_training_examples(examples)
        log(f"✅ Saved to {output_file}")
        
        # Statistics
        total_iocs = sum(ex['metadata']['ioc_count'] for ex in examples)
        total_mitre = sum(ex['metadata']['mitre_count'] for ex in examples)
        
        log(f"Training data generation complete:")
        log(f"  - {len(examples)} training examples")
        log(f"  - {total_iocs} total IOCs")
        log(f"  - {total_mitre} total MITRE techniques")
        log(f"  - Output: {output_file}")
        
        return {
            'success': True,
            'file_path': output_file,
            'example_count': len(examples),
            'ioc_count': total_iocs,
            'mitre_count': total_mitre
        }
        
    except Exception as e:
        error_msg = f"Failed to generate training data: {e}"
        log(f"❌ {error_msg}")
        logger.error(f"[AI Training] {error_msg}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }

