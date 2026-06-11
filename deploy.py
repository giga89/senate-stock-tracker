import paramiko
import os
import tarfile

def create_tarball():
    tar_name = "senate-stock-tracker.tar.gz"
    with tarfile.open(tar_name, "w:gz") as tar:
        for name in ["backend", "frontend", "data", "Dockerfile", "docker-compose.yml", "requirements.txt", ".env"]:
            if os.path.exists(name):
                tar.add(name)
    return tar_name

def deploy():
    host = "192.168.9.85"
    user = "orangepi"
    password = "orangepi"  # As provided by user
    
    print("Creating tarball...")
    tar_name = create_tarball()
    
    print(f"Connecting to {host}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password)
    
    sftp = ssh.open_sftp()
    
    remote_dir = "/home/orangepi/senate-stock-tracker"
    print(f"Creating directory {remote_dir}...")
    ssh.exec_command(f"mkdir -p {remote_dir}")
    
    print("Uploading files...")
    sftp.put(tar_name, f"{remote_dir}/{tar_name}")
    sftp.close()
    
    print("Extracting files and starting Docker (this might take a few minutes if it's building for the first time)...")
    commands = [
        f"cd {remote_dir}",
        f"tar -xzf {tar_name}",
        f"mkdir -p data",
        f"echo '{password}' | sudo -S docker compose up -d --build"
    ]
    
    stdin, stdout, stderr = ssh.exec_command(" && ".join(commands))
    
    # Read output line by line
    while True:
        line = stdout.readline()
        if not line:
            break
        print(line.strip())
        
    while True:
        err_line = stderr.readline()
        if not err_line:
            break
        print(f"ERR: {err_line.strip()}")
        
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("Deploy successful!")
    else:
        print("Deploy failed.")
        
    ssh.close()
    os.remove(tar_name)

if __name__ == "__main__":
    deploy()
