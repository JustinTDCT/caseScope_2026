"""
Utility functions for SIGMA rule management
"""
import os
import yaml
import logging
from pathlib import Path
from datetime import datetime
import subprocess

logger = logging.getLogger(__name__)


def list_sigma_rules(page=1, per_page=50, search_query=''):
    """
    List SIGMA rules from filesystem with pagination
    Includes: rules/windows, rules-dfir, rules-emerging-threats, rules-threat-hunting
    
    Args:
        page: Page number (1-indexed)
        per_page: Rules per page
        search_query: Search term for rule title/filename
    
    Returns:
        dict with: rules, total, page, per_page, total_pages
    """
    sigma_repo = Path('/opt/casescope/sigma_rules_repo')
    
    # Multiple rule directories to scan
    lolrmm_repo = Path('/opt/casescope/lolrmm')
    
    rule_paths = [
        sigma_repo / 'rules' / 'windows',           # Standard Windows detection rules
        sigma_repo / 'rules-dfir',                  # DFIR-specific rules
        sigma_repo / 'rules-emerging-threats',      # Latest emerging threats
        sigma_repo / 'rules-threat-hunting',        # Proactive threat hunting rules
        lolrmm_repo / 'detections' / 'sigma',       # magicsword-io/lolrmm RMM tool detections
    ]
    
    # Collect all .yml files with metadata
    all_rules = []
    
    for sigma_path in rule_paths:
        if not sigma_path.exists():
            logger.debug(f"SIGMA rules path not found (skipping): {sigma_path}")
            continue
        
        # Track which rule set this is from
        rule_set = sigma_path.name if sigma_path.name.startswith('rules-') else 'rules/windows'
        
        for root, dirs, files in os.walk(sigma_path):
            for filename in files:
                if not filename.endswith('.yml'):
                    continue
                
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, sigma_path)
                
                # Apply search filter
                if search_query:
                    if search_query.lower() not in filename.lower() and search_query.lower() not in rel_path.lower():
                        # Try to load YAML and search in title
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                rule_data = yaml.safe_load(f)
                                title = rule_data.get('title', '')
                                if search_query.lower() not in title.lower():
                                    continue
                        except:
                            continue
                
                # Parse YAML for metadata
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        rule_data = yaml.safe_load(f)
                    
                    rule = {
                        'filename': filename,
                        'filepath': rel_path,
                        'full_path': filepath,
                        'title': rule_data.get('title', filename),
                        'level': rule_data.get('level', 'unknown'),
                        'description': rule_data.get('description', ''),
                        'tags': rule_data.get('tags', []),
                        'status': rule_data.get('status', 'unknown'),
                        'rule_set': rule_set,  # Track which collection this rule is from
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath))
                    }
                    all_rules.append(rule)
                except Exception as e:
                    logger.debug(f"Could not parse rule {filepath}: {e}")
                    # Add basic info even if parsing fails
                    all_rules.append({
                        'filename': filename,
                        'filepath': rel_path,
                        'full_path': filepath,
                        'title': filename,
                        'level': 'unknown',
                        'description': f'Parse error: {str(e)}',
                        'tags': [],
                        'status': 'error',
                        'rule_set': rule_set,
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath))
                    })
    
    # Sort by level (critical > high > medium > low) then by title
    level_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'informational': 4, 'unknown': 5, 'error': 6}
    all_rules.sort(key=lambda x: (level_order.get(x['level'], 99), x['title']))
    
    # Pagination
    total = len(all_rules)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(1, min(page, total_pages))  # Clamp page to valid range
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    rules = all_rules[start_idx:end_idx]
    
    return {
        'rules': rules,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    }


def update_sigma_rules():
    """
    Update SIGMA rules from GitHub (git pull)
    
    Returns:
        dict with: success, message, output
    """
    sigma_repo = Path('/opt/casescope/sigma_rules_repo')
    
    if not sigma_repo.exists():
        return {
            'success': False,
            'message': 'SIGMA rules repository not found',
            'output': ''
        }
    
    try:
        # Git pull
        result = subprocess.run(
            ['git', 'pull'],
            cwd=str(sigma_repo),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            # Check if there were updates
            if 'Already up to date' in output or 'Already up-to-date' in output:
                message = 'SIGMA rules are already up to date'
            else:
                message = 'SIGMA rules updated successfully'
            
            logger.info(f"[SIGMA UPDATE] {message}")
            return {
                'success': True,
                'message': message,
                'output': output
            }
        else:
            logger.error(f"[SIGMA UPDATE] Git pull failed: {output}")
            return {
                'success': False,
                'message': 'Failed to update SIGMA rules',
                'output': output
            }
    
    except subprocess.TimeoutExpired:
        logger.error("[SIGMA UPDATE] Git pull timeout")
        return {
            'success': False,
            'message': 'Update timeout (60s)',
            'output': 'Operation timed out'
        }
    except Exception as e:
        logger.error(f"[SIGMA UPDATE] Error: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'output': str(e)
        }


def get_sigma_stats():
    """
    Get SIGMA statistics from all rule sets
    
    Returns:
        dict with: total_rules, last_updated, breakdown by rule set
    """
    from models import SigmaViolation
    from main import db
    
    sigma_repo = Path('/opt/casescope/sigma_rules_repo')
    
    # Multiple rule directories to count
    lolrmm_repo = Path('/opt/casescope/lolrmm')
    
    rule_paths = {
        'Windows Rules': sigma_repo / 'rules' / 'windows',
        'DFIR Rules': sigma_repo / 'rules-dfir',
        'Emerging Threats': sigma_repo / 'rules-emerging-threats',
        'Threat Hunting': sigma_repo / 'rules-threat-hunting',
        'RMM Detections': lolrmm_repo / 'detections' / 'sigma',
    }
    
    total_rules = 0
    rule_breakdown = {}
    last_updated = None
    
    for name, path in rule_paths.items():
        if path.exists():
            count = sum(1 for root, dirs, files in os.walk(path) 
                       for f in files if f.endswith('.yml'))
            rule_breakdown[name] = count
            total_rules += count
            
            # Get most recent modification time
            try:
                stat = os.stat(path)
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                if last_updated is None or mod_time > last_updated:
                    last_updated = mod_time
            except:
                pass
        else:
            rule_breakdown[name] = 0
    
    # Count violations
    total_violations = db.session.query(SigmaViolation).count()
    
    return {
        'total_rules': total_rules,
        'enabled_rules': total_rules,  # All rules are enabled by default
        'last_updated': last_updated,
        'total_violations': total_violations,
        'breakdown': rule_breakdown
    }

