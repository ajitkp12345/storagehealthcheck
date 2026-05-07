#!/usr/bin/env python3
"""
Storage Health Check Tool
A standalone executable for checking health of enterprise storage platforms.
Supports Pure Storage and NetApp ONTAP via REST APIs.
"""

import json
import sys
import getpass
import requests
from urllib3.exceptions import InsecureRequestWarning
import warnings

# Suppress SSL warnings for customer environments
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

class StorageHealthCheck:
    def __init__(self):
        self.results = []

    def display_menu(self):
        """Display the main menu and get user selection."""
        print("\n" + "="*50)
        print("Storage Health Check Tool")
        print("="*50)
        print("Select storage platform:")
        print("1. Pure Storage")
        print("2. NetApp ONTAP")
        print("3. Cisco UCS Manager")
        print("4. Exit")
        print("="*50)

        while True:
            try:
                choice = input("Enter your choice (1-4): ").strip()
                if choice == '1':
                    return 'pure'
                elif choice == '2':
                    return 'netapp'
                elif choice == '3':
                    return 'ucsm'
                elif choice == '4':
                    print("Exiting...")
                    sys.exit(0)
                else:
                    print("Invalid choice. Please enter 1, 2, 3, or 4.")
            except KeyboardInterrupt:
                print("\nExiting...")
                sys.exit(0)

    def get_credentials(self):
        """Prompt user for management IP/hostname and credentials."""
        print("\n" + "-"*40)
        print("Connection Details")
        print("-"*40)

        while True:
            ip = input("Management IP/Hostname: ").strip()
            if ip:
                break
            print("IP/Hostname cannot be empty.")

        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")

        return ip, username, password

    def _resolve_field(self, data, keys, default='Unknown'):
        """Return the first non-empty value from a list of keys."""
        for key in keys:
            value = data.get(key) if isinstance(data, dict) else None
            if value not in (None, ''):
                return value
        return default

    def _health_status(self, raw_status, default_as_critical=True):
        """Normalize a status value and return (status, display_value)."""
        if isinstance(raw_status, dict):
            raw_status = self._resolve_field(raw_status, ['status', 'state', 'health', 'online'])

        if isinstance(raw_status, bool):
            return ('OK' if raw_status else 'CRITICAL', str(raw_status))

        status_text = str(raw_status).strip()
        normalized = status_text.lower()

        if normalized in ['ok', 'healthy', 'online', 'up', 'active', 'true', 'available', 'ready', 'normal', 'operational']:
            return ('OK', status_text)
        if normalized in ['warning', 'degraded', 'partial', 'partially degraded', 'limited', 'alert']:
            return ('WARNING', status_text)
        if normalized == 'unknown' and not default_as_critical:
            return (None, status_text or 'Unknown')
        if normalized in ['critical', 'down', 'offline', 'false', 'unavailable', 'failed', 'error']:
            return ('CRITICAL', status_text)

        if default_as_critical:
            return ('CRITICAL', status_text or 'Unknown')
        return (None, status_text or 'Unknown')

    def _find_status_recursive(self, item):
        """Recursively search a structure for a known health status."""
        if isinstance(item, dict):
            for key, value in item.items():
                status, display_value = self._health_status(value, default_as_critical=False)
                if status is not None:
                    return status, display_value
                if isinstance(value, (dict, list)):
                    nested_status = self._find_status_recursive(value)
                    if nested_status is not None:
                        return nested_status
        elif isinstance(item, list):
            for value in item:
                status, display_value = self._health_status(value, default_as_critical=False)
                if status is not None:
                    return status, display_value
                if isinstance(value, (dict, list)):
                    nested_status = self._find_status_recursive(value)
                    if nested_status is not None:
                        return nested_status
        return None

    def _extract_status(self, item):
        """Extract a status from a record using known fields and nested values."""
        if not isinstance(item, dict):
            return ('CRITICAL', 'Unknown')

        status_value = self._resolve_field(item, ['state', 'health', 'status', 'online', 'is_online', 'service_state', 'volume_state', 'operational_state'])
        status, display_value = self._health_status(status_value, default_as_critical=False)
        if status is not None:
            return status, display_value

        nested = self._find_status_recursive(item)
        if nested is not None:
            return nested

        return ('CRITICAL', 'Unknown')

    def _get_json_from_endpoints(self, session, base_url, paths):
        """Try a list of endpoint paths and return the first JSON result."""
        for path in paths:
            try:
                response = session.get(f"{base_url}{path}", timeout=10)
                if response.status_code == 200:
                    return response.json()
            except requests.exceptions.RequestException:
                continue
        return None

    def _summarize_records(self, data, keys):
        """Summarize record statuses from JSON data using candidate keys."""
        records = []
        if isinstance(data, dict):
            if 'records' in data and isinstance(data['records'], list):
                records = data['records']
            else:
                records = [data]
        elif isinstance(data, list):
            records = data

        counts = {'OK': 0, 'WARNING': 0, 'CRITICAL': 0}
        for record in records:
            value = self._resolve_field(record, keys, 'Unknown')
            status, _ = self._health_status(value)
            counts[status] += 1

        return counts, len(records)

    def check_pure_storage(self, ip, username, password, auth_type='password'):
        """Perform health checks on Pure Storage array."""
        base_url = f"https://{ip}/api/1.19"
        session = requests.Session()
        session.headers.update({'Accept': 'application/json'})
        if auth_type == 'token':
            session.headers.update({'X-Auth-Token': password})
        else:
            session.auth = (username, password)
        session.verify = False

        checks = []

        try:
            # Check array info
            response = session.get(f"{base_url}/array")
            if auth_type == 'token' and response.status_code == 401:
                # Try alternate token header if the Pure API uses a bearer-style header
                session.headers.pop('X-Auth-Token', None)
                session.headers.update({'Authorization': f'Bearer {password}'})
                response = session.get(f"{base_url}/array")

            response.raise_for_status()
            array_data = response.json()

            # Array operational state
            node_status = array_data.get('status', array_data.get('health', 'Unknown'))
            status, display_value = self._health_status(node_status)
            checks.append({
                'platform': 'Pure Storage',
                'component': 'Array',
                'check_name': 'Operational State',
                'value': display_value,
                'status': status,
                'recommended_action': 'Contact Pure Storage support if not ready'
            })

            # Capacity usage
            total_capacity = array_data.get('capacity', 0)
            used_capacity = array_data.get('total', 0)
            if total_capacity > 0:
                usage_percent = (used_capacity / total_capacity) * 100
                status = 'OK' if usage_percent < 80 else 'WARNING' if usage_percent < 95 else 'CRITICAL'
                checks.append({
                    'platform': 'Pure Storage',
                    'component': 'Capacity',
                    'check_name': 'Capacity Usage',
                    'value': f"{usage_percent:.1f}%",
                    'status': status,
                    'recommended_action': 'Monitor capacity growth and plan expansion if needed'
                })

            # Hardware health
            response = session.get(f"{base_url}/hardware")
            if response.status_code == 200:
                hardware_data = response.json()
                for hw in hardware_data:
                    hw_status = hw.get('status', hw.get('health', 'Unknown'))
                    status, display_value = self._health_status(hw_status)
                    checks.append({
                        'platform': 'Pure Storage',
                        'component': 'Hardware',
                        'check_name': f"{hw.get('name', 'Unknown')} Status",
                        'value': display_value,
                        'status': status,
                        'recommended_action': 'Replace faulty hardware component'
                    })

        except requests.exceptions.RequestException as e:
            checks.append({
                'platform': 'Pure Storage',
                'component': 'Connection',
                'check_name': 'API Connectivity',
                'value': f"Failed: {str(e)}",
                'status': 'CRITICAL',
                'recommended_action': 'Verify IP, credentials, and network connectivity'
            })

        return checks

    def check_netapp_ontap(self, ip, username, password):
        """Perform health checks on NetApp ONTAP cluster."""
        base_url = f"https://{ip}/api"
        session = requests.Session()
        session.auth = (username, password)
        session.verify = False
        session.headers.update({'Accept': 'application/json'})

        checks = []

        try:
            # Check cluster info
            response = session.get(f"{base_url}/cluster")
            response.raise_for_status()
            cluster_data = response.json()

            # Cluster health
            status, display_value = self._extract_status(cluster_data)
            checks.append({
                'platform': 'NetApp ONTAP',
                'component': 'Cluster',
                'check_name': 'Cluster Health',
                'value': display_value,
                'status': status,
                'recommended_action': 'Check cluster logs and node status'
            })

            # Node health
            response = session.get(f"{base_url}/cluster/nodes")
            if response.status_code == 200:
                nodes_data = response.json()
                for node in nodes_data.get('records', []):
                    status, display_value = self._extract_status(node)
                    checks.append({
                        'platform': 'NetApp ONTAP',
                        'component': 'Node',
                        'check_name': f"{node.get('name', 'Unknown')} Health",
                        'value': display_value,
                        'status': status,
                        'recommended_action': 'Investigate node issues'
                    })

            # Aggregate status
            response = session.get(f"{base_url}/storage/aggregates")
            if response.status_code == 200:
                agg_data = response.json()
                for agg in agg_data.get('records', []):
                    status, display_value = self._extract_status(agg)
                    checks.append({
                        'platform': 'NetApp ONTAP',
                        'component': 'Aggregate',
                        'check_name': f"{agg.get('name', 'Unknown')} State",
                        'value': display_value,
                        'status': status,
                        'recommended_action': 'Bring aggregate online or investigate issues'
                    })

            # Volume status
            response = session.get(f"{base_url}/storage/volumes")
            if response.status_code == 200:
                vol_data = response.json()
                for vol in vol_data.get('records', []):
                    status, display_value = self._extract_status(vol)
                    checks.append({
                        'platform': 'NetApp ONTAP',
                        'component': 'Volume',
                        'check_name': f"{vol.get('name', 'Unknown')} State",
                        'value': display_value,
                        'status': status,
                        'recommended_action': 'Bring volume online or investigate issues'
                    })

        except requests.exceptions.RequestException as e:
            checks.append({
                'platform': 'NetApp ONTAP',
                'component': 'Connection',
                'check_name': 'API Connectivity',
                'value': f"Failed: {str(e)}",
                'status': 'CRITICAL',
                'recommended_action': 'Verify IP, credentials, and network connectivity'
            })

        return checks

    def check_ucs_manager(self, ip, username, password):
        """Perform health checks on Cisco UCS Manager."""
        base_url = f"https://{ip}"
        session = requests.Session()
        session.auth = (username, password)
        session.verify = False
        session.headers.update({'Accept': 'application/json'})

        checks = []

        try:
            faults = self._get_json_from_endpoints(session, base_url, [
                '/api/faults', '/faults', '/api/health/faults', '/health/faults',
                '/faultSummary', '/api/faultSummary'
            ])
            if faults is not None:
                counts, total = self._summarize_records(faults, ['severity', 'faultSeverity', 'level', 'status'])
                status = 'OK' if counts['CRITICAL'] == 0 and total > 0 else 'WARNING' if counts['WARNING'] > 0 else 'CRITICAL'
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'Fault Summary',
                    'check_name': 'Fault summary by severity',
                    'value': f"OK={counts['OK']} WARNING={counts['WARNING']} CRITICAL={counts['CRITICAL']} ({total} total)",
                    'status': status,
                    'recommended_action': 'Review UCS fault severity and clear or escalate any critical faults'
                })
            else:
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'Fault Summary',
                    'check_name': 'Fault summary by severity',
                    'value': 'No fault summary returned',
                    'status': 'WARNING',
                    'recommended_action': 'Verify UCS Manager fault API endpoint or credentials'
                })

            blades = self._get_json_from_endpoints(session, base_url, [
                '/api/blades', '/blades', '/inventory/blades', '/servers', '/inventory/servers'
            ])
            if blades is not None:
                counts, total = self._summarize_records(blades, ['operability', 'status', 'health', 'state'])
                status = 'OK' if counts['CRITICAL'] == 0 else 'WARNING' if counts['WARNING'] > 0 else 'CRITICAL'
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'Blade/Server',
                    'check_name': 'Blade/server operability',
                    'value': f"OK={counts['OK']} WARNING={counts['WARNING']} CRITICAL={counts['CRITICAL']} ({total} total)",
                    'status': status,
                    'recommended_action': 'Investigate any blades or servers that are not operable'
                })
            else:
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'Blade/Server',
                    'check_name': 'Blade/server operability',
                    'value': 'No blade/server data returned',
                    'status': 'WARNING',
                    'recommended_action': 'Verify UCS Manager blade/server API endpoint or credentials'
                })

            psus = self._get_json_from_endpoints(session, base_url, [
                '/api/psus', '/inventory/power-supplies', '/power-supplies', '/status/psus'
            ])
            fans = self._get_json_from_endpoints(session, base_url, [
                '/api/fans', '/inventory/fans', '/fans', '/status/fans'
            ])
            combined_counts = {'OK': 0, 'WARNING': 0, 'CRITICAL': 0}
            total_equipment = 0
            if psus is not None:
                psu_counts, psu_total = self._summarize_records(psus, ['status', 'health', 'state', 'operability'])
                total_equipment += psu_total
                for key in combined_counts:
                    combined_counts[key] += psu_counts[key]
            if fans is not None:
                fan_counts, fan_total = self._summarize_records(fans, ['status', 'health', 'state', 'operability'])
                total_equipment += fan_total
                for key in combined_counts:
                    combined_counts[key] += fan_counts[key]
            if total_equipment > 0:
                status = 'OK' if combined_counts['CRITICAL'] == 0 else 'WARNING' if combined_counts['WARNING'] > 0 else 'CRITICAL'
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'PSU/FAN',
                    'check_name': 'PSU / FAN status',
                    'value': f"OK={combined_counts['OK']} WARNING={combined_counts['WARNING']} CRITICAL={combined_counts['CRITICAL']} ({total_equipment} total)",
                    'status': status,
                    'recommended_action': 'Check power supplies and fans for any degraded or failed components'
                })
            else:
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'PSU/FAN',
                    'check_name': 'PSU / FAN status',
                    'value': 'No PSU/FAN data returned',
                    'status': 'WARNING',
                    'recommended_action': 'Verify UCS Manager PSU/FAN endpoint or credentials'
                })

            fi_data = self._get_json_from_endpoints(session, base_url, [
                '/api/fis', '/fabric-interconnects', '/cluster/fis', '/status/fis'
            ])
            if fi_data is not None:
                if isinstance(fi_data, list):
                    counts, total = self._summarize_records(fi_data, ['status', 'health', 'state', 'operability'])
                    status = 'OK' if counts['CRITICAL'] == 0 else 'WARNING' if counts['WARNING'] > 0 else 'CRITICAL'
                    value = f"OK={counts['OK']} WARNING={counts['WARNING']} CRITICAL={counts['CRITICAL']} ({total} total)"
                else:
                    status, display_value = self._extract_status(fi_data)
                    value = display_value
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'FI Cluster',
                    'check_name': 'FI cluster state',
                    'value': value,
                    'status': status,
                    'recommended_action': 'Verify fabric interconnect cluster state and investigate any failures'
                })
            else:
                checks.append({
                    'platform': 'Cisco UCS Manager',
                    'component': 'FI Cluster',
                    'check_name': 'FI cluster state',
                    'value': 'No FI cluster data returned',
                    'status': 'WARNING',
                    'recommended_action': 'Verify UCS Manager FI cluster endpoint or credentials'
                })

        except requests.exceptions.RequestException as e:
            checks.append({
                'platform': 'Cisco UCS Manager',
                'component': 'Connection',
                'check_name': 'API Connectivity',
                'value': f"Failed: {str(e)}",
                'status': 'CRITICAL',
                'recommended_action': 'Verify IP, credentials, and network connectivity'
            })

        return checks

    def display_results(self, checks):
        """Display health check results in a summarized component view."""
        print("\n" + "="*80)
        print("HEALTH CHECK RESULTS")
        print("="*80)

        summary = {}
        for check in checks:
            key = (check['platform'], check['component'])
            if key not in summary:
                summary[key] = {'OK': 0, 'WARNING': 0, 'CRITICAL': 0}
            summary[key][check['status']] += 1

        for (platform, component), counts in summary.items():
            print(f"{platform} / {component}: OK={counts['OK']} WARNING={counts['WARNING']} CRITICAL={counts['CRITICAL']}")
        print("="*80)

        for check in checks:
            print(f"Platform: {check['platform']}")
            print(f"Component: {check['component']}")
            print(f"Check: {check['check_name']}")
            print(f"Value: {check['value']}")
            print(f"Status: {check['status']}")
            if check['status'] != 'OK':
                print(f"Action: {check['recommended_action']}")
            print("-"*40)

    def save_report(self, checks, platform):
        """Save results to JSON file."""
        filename = f"storage_health_report_{platform.replace(' ', '_').lower()}.json"
        with open(filename, 'w') as f:
            json.dump(checks, f, indent=2)
        print(f"\nReport saved to: {filename}")

    def run(self):
        """Main execution loop."""
        while True:
            platform = self.display_menu()

            ip, username, password = self.get_credentials()

            auth_type = 'password'  # default
            if platform == 'pure':
                print("Pure Storage Authentication:")
                print("1. Username/Password")
                print("2. API Token")
                while True:
                    auth_choice = input("Enter choice (1-2): ").strip()
                    if auth_choice == '1':
                        auth_type = 'password'
                        break
                    elif auth_choice == '2':
                        auth_type = 'token'
                        break
                    else:
                        print("Invalid choice.")

            print(f"\nConnecting to {platform.upper()} at {ip}...")

            if platform == 'pure':
                checks = self.check_pure_storage(ip, username, password, auth_type)
            elif platform == 'netapp':
                checks = self.check_netapp_ontap(ip, username, password)
            elif platform == 'ucsm':
                checks = self.check_ucs_manager(ip, username, password)

            self.display_results(checks)
            self.save_report(checks, platform)

            print("\nPress Enter to continue or Ctrl+C to exit...")
            try:
                input()
            except KeyboardInterrupt:
                print("\nExiting...")
                break

if __name__ == "__main__":
    checker = StorageHealthCheck()
    checker.run()