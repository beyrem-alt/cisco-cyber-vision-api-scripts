#!/usr/bin/python3
# Cisco Cyber Vision V4.0
# Capture Mode Management

import argparse
import csv
import cvconfig
import api
import os


def main():
    parser = argparse.ArgumentParser(
        prog="capture_mode.py",
        description="Sensor Capture Mode Management"
    )

    # General options
    parser.add_argument("--token", dest="token", help="Use this token")
    parser.add_argument("--center-ip", dest="center_ip",
                        help="Specify the Center FQDN or IPv4 address "
                             "(default: 'cybervision')")
    parser.add_argument("--center-port", dest="center_port",
                        help=f"Specify the Center port (default: {cvconfig.center_port})",
                        default=cvconfig.center_port)
    parser.add_argument("--proxy", dest="proxy",
                        help=f"Specify the proxy to use (default: {cvconfig.proxy})",
                        default=cvconfig.proxy)
    parser.add_argument("--encoding", dest="csv_encoding",
                        help=f"CSV file encoding (default: {cvconfig.csv_encoding})",
                        default=cvconfig.csv_encoding)
    parser.add_argument("--delimiter", dest="csv_delimiter",
                        help=f"CSV file delimiter (default: {cvconfig.csv_delimiter})",
                        default=cvconfig.csv_delimiter)

    # CSV filename (new option)
    parser.add_argument("--file", dest="csv_file",
                        help="Specify custom CSV filename (default: sensor_list.csv)",
                        default="sensor_list.csv")

    # Filter (optional argument)
    parser.add_argument("--filter", dest="filter",
                        nargs="?", const="optimal", default="optimal",
                        help="Specify capture filter ('all', 'optimal', 'industrial_only' or custom). "
                             "Default: 'optimal'")

    # Main command group
    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument("--capush",
                               help="Push capture mode filter. Default is 'optimal', or specify with --filter.",
                               action="store_true", dest="command_capture")
    command_group.add_argument("--list",
                               help="Display sensors list and write to a CSV file with pre-filled filter column.",
                               action="store_true", dest="command_list")
    command_group.add_argument("--capushcsv",
                               help="Push capture mode filter using values from CSV file (default: sensor_list.csv).",
                               action="store_true", dest="command_capushcsv")

    args = parser.parse_args()

    # Configuration handling
    token = set_conf(args.token, cvconfig.token)
    center_ip = set_conf(args.center_ip, cvconfig.center_ip)
    center_port = set_conf(args.center_port, cvconfig.center_port)
    proxy = set_conf(args.proxy, cvconfig.proxy)
    csv_encoding = set_conf(args.csv_encoding, cvconfig.csv_encoding)
    csv_delimiter = set_conf(args.csv_delimiter, cvconfig.csv_delimiter)
    filter_str = set_conf(args.filter, "optimal")
    sensor_filename = args.csv_file

    if not token or not center_ip:
        print("ERROR: TOKEN and CENTER_IP are mandatory. "
              "Check cvconfig.py or use --token/--center-ip options.")
        return

    if args.command_capture:
        return sensor_cap_push(center_ip, center_port, token, proxy,
                               sensor_filename, csv_delimiter, csv_encoding, filter_str)
    elif args.command_list:
        return get_sensor_ids(center_ip, center_port, token, proxy,
                              sensor_filename, csv_delimiter, csv_encoding)
    elif args.command_capushcsv:
        return sensor_cap_push_from_csv(center_ip, center_port, token, proxy,
                                        sensor_filename, csv_delimiter, csv_encoding)

    parser.print_help()


def set_conf(arg, conf):
    """Return argument if provided, otherwise default from config."""
    if arg and arg != conf:
        return arg
    return conf


def sensor_cap_push(center_ip, center_port, token, proxy,
                    filename, csv_delimiter, csv_encoding, filter_str="optimal"):
    """Push a single filter to all sensors."""
    with api.APISession(center_ip, center_port, token, proxy) as session:
        sensors = api.get_route(session, '/api/3.0/sensors')
        if not sensors:
            print("No sensors found.")
            return

        print(f"\n=== Sensors Found ({len(sensors)}) ===")
        for s in sensors:
            print(f"  - {s.get('id')} ({s.get('model', 'Unknown')})")

        # Write to CSV with filter column
        with open(filename, "w", newline="", encoding=csv_encoding) as csvfile:
            writer = csv.writer(csvfile, delimiter=csv_delimiter)
            writer.writerow(["id", "name", "model", "status", "filter"])
            for s in sensors:
                writer.writerow([
                    s.get("id"),
                    s.get("name"),
                    s.get("model"),
                    s.get("status", {}).get("operationalStatus", "N/A"),
                    filter_str
                ])
        print(f"\nSensor list with filter saved to {filename}")

        # Push filter
        print(f"\nPushing filter '{filter_str}' to sensors...")
        for s in sensors:
            sensor_id = s.get("id")
            model = s.get("model", "Unknown")
            name = s.get("name", "Unknown")

            # Skip unsupported model
            if model.upper() == "PCAP":
                print(f"⚠️  Skipping {sensor_id} (model={model}): capture mode not supported.")
                continue

            route = f"/api/3.0/sensors/{sensor_id}/capture-mode"
            payload = {"filter": filter_str}

            try:
                response = api.post_route(session, route, payload)
                try:
                    data = response.json()
                    msg = data.get("message", response.text)
                except Exception:
                    msg = response.text.strip() or f"HTTP {response.status_code}"

                if response.status_code != 200:
                    print(f"❌ Not updated {name}:  {msg}")
                else:
                    print(f"✅ Updated {name}: filter='{filter_str}'")

            except Exception as e:
                print(f"❌ Failed to update {sensor_id}: {e}")

        print("\nDone.")
        return [s.get("id") for s in sensors]


def sensor_cap_push_from_csv(center_ip, center_port, token, proxy,
                             filename, csv_delimiter, csv_encoding):
    """Push filters to sensors based on CSV file content."""
    if not os.path.exists(filename):
        print(f"CSV file '{filename}' not found. Run --list first.")
        return

    with open(filename, "r", encoding=csv_encoding) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=csv_delimiter)
        rows = list(reader)

    if not rows or "id" not in reader.fieldnames or "filter" not in reader.fieldnames:
        print(f"CSV file must contain 'id' and 'filter' columns.")
        return

    print(f"\nProcessing {len(rows)} sensors from '{filename}'...")

    with api.APISession(center_ip, center_port, token, proxy) as session:
        for row in rows:
            sensor_id = row["id"]
            model = row.get("model", "").upper()
            name = row.get("name", "Unknown")
            filter_val = row.get("filter", "optimal") or "optimal"

            if model == "PCAP":
                print(f"⚠️  Skipping {sensor_id} (model={model}): capture mode not supported.")
                continue

            route = f"/api/3.0/sensors/{sensor_id}/capture-mode"
            payload = {"filter": filter_val}
            try:
                response = api.post_route(session, route, payload)
                try:
                    data = response.json()
                    msg = data.get("message", response.text)
                except Exception:
                    msg = response.text.strip() or f"HTTP {response.status_code}"

                if response.status_code != 200:
                    print(f"❌ Not updated {name}:  {msg}")
                else:
                    print(f"✅ Updated {name}: filter='{filter_val}'")

            except Exception as e:
                print(f"❌ Failed to update {sensor_id}: {e}")


def get_sensor_ids(center_ip, center_port, token, proxy,
                   filename, csv_delimiter, csv_encoding):
    """Retrieve and print sensor list from API and save with filter column."""
    with api.APISession(center_ip, center_port, token, proxy) as session:
        sensors = api.get_route(session, '/api/3.0/sensors')
        if not sensors:
            print("No sensors found.")
            return []

        print(f"\n=== Retrieved {len(sensors)} Sensors ===")
        with open(filename, "w", newline="", encoding=csv_encoding) as csvfile:
            writer = csv.writer(csvfile, delimiter=csv_delimiter)
            writer.writerow(["id", "name", "model", "status", "filter"])

            for s in sensors:
                sensor_id = s.get("id", "N/A")
                name = s.get("name", "Unknown")
                model = s.get("model", "Unknown")
                status = s.get("status", {}).get("operationalStatus", "Unknown")
                enrollment = s.get("status", {}).get("enrollmentStatus", "Unknown")

                print(f"- ID: {sensor_id}")
                print(f"  Name: {name}")
                print(f"  Model: {model}")
                print(f"  Enrollment: {enrollment}")
                print(f"  Status: {status}")
                print("-" * 50)

                writer.writerow([sensor_id, name, model, status, "optimal"])

        print(f"\nSensor list with default filter saved to {filename}")
        return [s.get("id") for s in sensors]


if __name__ == "__main__":
    main()
