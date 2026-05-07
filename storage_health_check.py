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
        print("3. Exit")
        print("="*50)

        while True:
            try:
                choice = input("Enter your choice (1-3): ").strip()
                if choice == '1':
                    return 'pure'
                elif choice == '2':
                    return 'netapp'
                elif choice == '3':
                    print("Exiting...")
                    sys.exit(0)
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
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

    def _health_status(self, raw_status):
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
        if normalized in ['critical', 'down', 'offline', 'false', 'unavailable', 'failed', 'error', 'unknown']:
            return ('CRITICAL', status_text)

        return ('CRITICAL', status_text or 'Unknown')

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
            cluster_status = cluster_data.get('health', cluster_data.get('status', cluster_data.get('state', 'Unknown')))
            status, display_value = self._health_status(cluster_status)
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
                    node_status = node.get('health', node.get('status', node.get('state', 'Unknown')))
                    status, display_value = self._health_status(node_status)
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
                    agg_status = self._resolve_field(agg, ['state', 'health', 'status', 'online'])
                    status, display_value = self._health_status(agg_status)
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
                    vol_status = self._resolve_field(vol, ['state', 'health', 'status', 'online', 'is_online'])
                    status, display_value = self._health_status(vol_status)
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

    def display_results(self, checks):
        """Display health check results in a formatted way."""
        print("\n" + "="*80)
        print("HEALTH CHECK RESULTS")
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