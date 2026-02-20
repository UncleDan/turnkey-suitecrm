#!/usr/bin/python3
"""Set SuiteCRM admin password

Option:
    --pass=    unless provided, will ask interactively
    --domain=  unless provided, will ask interactively
               DEFAULT=www.example.com
"""

import sys
import getopt
import os
from hashlib import md5
import subprocess

from libinithooks.dialog_wrapper import Dialog
from mysqlconf import MySQL

DEFAULT_DOMAIN = "www.example.com"
WEBROOT = "/var/www/suitecrm"
CONF_FILE = "/etc/apache2/sites-available/suitecrm.conf"

def usage(s=None):
    if s:
        print("Error:", s, file=sys.stderr)
    print(f"Syntax: {sys.argv[0]} [options]", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    sys.exit(1)

def is_ssl_enabled():
    """Checks if SSL is active in the Apache config"""
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            if "SSLEngine on" in f.read():
                return True
    return False

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help', 'pass=', 'domain='])
    except getopt.GetoptError as e:
        usage(e)

    password = ""
    domain = ""
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass':
            password = val
        elif opt == '--domain':
            domain = val

    if not password:
        d = Dialog('TurnKey Linux - First boot configuration')
        password = d.get_password(
            "SuiteCRM Password",
            "Enter new password for the SuiteCRM 'admin' account.")

    if not domain:
        if 'd' not in locals():
            d = Dialog('TurnKey Linux - First boot configuration')

        domain = d.get_input(
            "SuiteCRM Domain",
            "Enter the domain to serve SuiteCRM.",
            DEFAULT_DOMAIN)

    if domain == "DEFAULT":
        domain = DEFAULT_DOMAIN

    # 1. SSL Detection & site_url Construction
    # Remove any existing protocol if user typed it in
    domain_clean = domain.replace('http://', '').replace('https://', '').strip('/')
    protocol = "https" if is_ssl_enabled() else "http"
    site_url = f"{protocol}://{domain_clean}"

    # 2. Update Legacy Configs
    for conf_name in ['config.php', 'config_si.php']:
        conf_path = f'{WEBROOT}/public/legacy/{conf_name}'
        if not os.path.exists(conf_path):
            continue
            
        with open(conf_path, 'r') as fob:
            lines = fob.readlines()
        
        with open(conf_path, 'w') as fob:
            for line in lines:
                if "'site_url'" in line:
                    fob.write(f"  'site_url' => '{site_url}',\n")
                else:
                    fob.write(line)

    # 3. Update Database Password
    # SuiteCRM 8 still uses BCRYPT(MD5(password)) for legacy compatibility
    password_md5 = md5(password.encode()).hexdigest()
    hash_pass = subprocess.run([
        'php', '-r', 'echo password_hash($argv[1], PASSWORD_BCRYPT);',
        password_md5
    ], capture_output=True, text=True).stdout.strip()

    m = MySQL()
    m.execute('UPDATE suitecrm.users SET user_hash=%s WHERE user_name="admin";', (hash_pass,))

    # 4. Clear Symfony Cache (Crucial for SuiteCRM 8 routing)
    # This prevents the 500 error after changing environmental settings
    subprocess.run(['sudo', '-u', 'www-data', f'{WEBROOT}/bin/console', 'cache:clear', '--no-warmup'], 
                   cwd=WEBROOT, capture_output=True)

    print(f"SuiteCRM 8 configuration updated for {site_url}")

if __name__ == "__main__":
    main()