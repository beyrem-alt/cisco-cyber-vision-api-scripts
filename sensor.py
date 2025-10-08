#!/usr/bin/python3
# Cisco Cyber Vision V4.0
# Group Management
import argparse
import requests
import json
import csv
import sys

import cvconfig
import api

def main():
    parser = argparse.ArgumentParser(prog="sensor.py",
                                     description="Sensor Management")
    # Options parsing
    parser.add_argument("--token", dest="token", help="Use this token")
    parser.add_argument("--center-ip", dest="center_ip",
                        help="Specified the center FQDN or IPv4 address"
                        " (default:'cybervision')")
    parser.add_argument("--center-port", dest="center_port",
                        help="Specified the center port (default: %d)"%cvconfig.center_port, 
                        default=cvconfig.center_port)
    parser.add_argument("--proxy", dest="proxy",
                        help="Specified the proxy to use (default: %s)"%cvconfig.proxy, 
                        default=cvconfig.proxy)
    parser.add_argument("--encoding", dest="csv_encoding",
                        help="CSV file encoding, default is %s" % cvconfig.csv_encoding)
    parser.add_argument("--delimiter", dest="csv_delimiter",
                        help="CSV file delimiter, default is %s" % cvconfig.csv_delimiter)
    
    parser.add_argument("--filter", dest="filter", help="Use this to pre fill desired filter for capture mode \n options: 'all', 'optimal' and 'industrial_only' DEFAULT 'all ", default="all")
    # Main Command Parsing
    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument("--list",
                               help="list all sensor configured on this  into a file\n",
                               action="store_true", default=False, dest="command_list")
    command_group.add_argument("--capture",
                               help="push custom capture mode from a file\n",
                               action="store_true", default=False, dest="command_capture")



    args = parser.parse_args()

    # Handle Cybervision configuration
    token = set_conf(args.token, cvconfig.token)
    center_ip = set_conf(args.center_ip, cvconfig.center_ip)
    center_port = set_conf(args.center_port, cvconfig.center_port)
    proxy = set_conf(args.proxy, cvconfig.proxy)
    csv_encoding = set_conf(args.csv_encoding, cvconfig.csv_encoding)
    csv_delimiter = set_conf(args.csv_delimiter, cvconfig.csv_delimiter)
    sensor_filename = "sensor_list.csv"
    filter = set_conf(args.filter, "all")

    if not token or not center_ip:
        print("TOKEN and CENTER_IP are mandatory, check cvconfig.py or us --token/--center-ip")

    if args.command_list:
        return sensor_list(center_ip, center_port, token, proxy, sensor_filename ,filter, csv_delimiter, csv_encoding)
    elif args.command_capture:
        return set_capture_mode(center_ip, center_port, token, proxy, sensor_filename,  csv_delimiter, csv_encoding)

    parser.print_help()

def set_conf(arg,conf):
    if arg and arg != conf:
        return arg
    return conf


    

import csv

def sensor_list(center_ip, center_port, token, proxy, filename, filter, csv_delimiter=',', csv_encoding='utf-8'):
    with api.APISession(center_ip, center_port, token, proxy) as session:
        sensors = api.get_route(session, '/api/3.0/sensors')
        
        if not sensors:
            print("No sensor data received.")
            return
        
        # Write to CSV with 'filter' column
        with open(filename, mode='w', newline='', encoding=csv_encoding) as csvfile:
            fieldnames = ['id', 'operationalStatus', 'name', 'model', 'filter']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=csv_delimiter)
            writer.writeheader()
            
            for sensor in sensors:
                sensor_id = sensor.get('id', '')
                name = sensor.get('name', '')
                model = sensor.get('model', '')
                operational_status = sensor.get('status', {}).get('operationalStatus', '')
                
                # Default filter is empty string
                writer.writerow({
                    'id': sensor_id,
                    'operationalStatus': operational_status,
                    'name': name,
                    'model': model,
                    'filter': filter
                })
        
        print(f"✅ Sensor data (with filter column) written to '{filename}'.")
    return


import csv
import json

def set_capture_mode(center_ip, center_port, token, proxy, csv_filename, csv_delimiter=',', csv_encoding='utf-8'):
    sensors = []
    try:
        with open(csv_filename, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                model = row.get('model', '')
                status = row.get('operationalStatus', '')
                sensor_filter = row.get('filter', '').strip()
                if model != 'PCAP' and status == 'CONNECTED' and sensor_filter:
                    sensors.append({
                        'id': row['id'],
                        'filter': sensor_filter
                    })
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        if e.__str__().__contains__("No such file or directory"):
            print("Make sure to create the file with --list first.")
        return

    if not sensors:
        print("⚠️ No matching sensors found with valid filters.")
        print("Make sure to fill the 'filter' column in the CSV file.")
        return

    # Send POST requests per sensor
    with api.APISession(center_ip, center_port, token, proxy) as session:
        for sensor in sensors:
            sensor_id = sensor['id']
            filter_str = sensor['filter']
            route = f"/api/3.0/sensors/{sensor_id}/capture-mode"
            payload = {"filter": filter_str}

            try:
                response = api.post_route(session, route, payload)
                if response.status_code != 200:
                    print(f"❌ Failed to update sensor {sensor_id}: {response.status_code} {response.text}")
                else:
                    print(f"✅ Sensor {sensor_id} updated successfully: {response}")
            except Exception as e:
                print(f"❌ Error updating sensor {sensor_id}: {e}")

    print("🎯 Capture mode update completed.")
    return


    

if __name__ == "__main__":
    main()