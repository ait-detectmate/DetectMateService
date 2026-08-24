#!/bin/bash

AUTO_YES=false
if [[ "$1" == "-y" ]]; then
    AUTO_YES=true
fi

release=$(lsb_release -a)
if [[ "$(lsb_release -is)" != "Ubuntu" ||
      "$(lsb_release -rs)" != "24.04" ||
      "$(lsb_release -cs)" != "noble" ]]; then
  echo "WARNING: Current OS is not Ubuntu 24.04.4 LTS (noble). This script may not work as intended."
  echo "Current OS:"
  echo "$release"
  if $AUTO_YES; then
    answer="y"
  else
    read -p "Continue? [y/n] " answer
  fi
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

rm -rf /tmp/DetectMateService

echo
echo "In this tutorial we want to find anomalies in nginx access.logs. So let's install nginx."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
sudo apt update && sudo apt install nginx -y

echo
echo "Send HTTP-request to our local nginx (curl http://localhost)."
echo
curl http://localhost
echo

echo "Now we should have at least one line in /var/log/nginx/access.log (tail -n 10):"
echo
sudo tail -n 10 /var/log/nginx/access.log
echo

echo "We need Docker and Docker Compose for the deployment. A comprehensive tutorial about how to install Docker can be found at https://docs.docker.com/engine/install/ubuntu/"
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo
echo "First run the following command to uninstall all conflicting packages:"
echo
echo "sudo apt remove \$(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc | cut -f1)"
echo
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc | cut -f1)
echo
echo "Now set up Docker's apt repository:"
cat <<EOF

# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

EOF

# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

echo
echo "Install docker and docker compose:"
echo "sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
echo
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
echo

echo "With Docker compose working, we will now download the DetectmateService repository using git:"
echo "cd /tmp && git clone https://github.com/ait-detectmate/DetectMateService.git && cd DetectMateService"
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo
cd /tmp && git clone https://github.com/ait-detectmate/DetectMateService.git
echo

echo "Let's start the default pipeline, just to test it:"
echo "sudo docker compose up -d"
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo
sudo docker compose up -d
echo
echo "To check the status of the containers, we can use docker compose ps:"
echo
sudo docker compose ps
echo
echo "Notice that the pipeline has **two** detector services running side by side: detector (running NewValueDetector) and detector-rule (running RuleDetector). The parser sends every parsed log line to both, and fluentout writes each detector's alerts to its own output file (output.%Y%m%d and output-rule.%Y%m%d)."
echo
echo "For now, we will shutdown all containers:"
echo "sudo docker compose down -v"
echo
sudo docker compose down -v
echo

echo "We have finally all requirements installed and have a boilerplate template for docker compose that starts an initial pipeline. In the next sections we will reconfigure that pipeline so that we can read the access.log and generate anomalies."
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo
echo "The preconfigured pipeline reads logs from container/fluentlogs/some.log. In order to be able to read the nginx access.log file, we need to mount /var/log/nginx into the fluentin container and modify the fluentd config so that it reads access.log instead."
echo "Initially we edit the docker-compose.yml and change only the fluentin volume mount to use /var/log/nginx."
echo
cat /tmp/DetectMateService/docker-compose.yml
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo
echo "Now that the access.logs are available in the container, we have to point fluentd to read that file. We need to edit the file container/fluentin/fluent.conf and replace path /fluentd/log/some.log with path /fluentd/log/access.log:"
echo
sed '1,/# --8<-- [start:tutorial]/d; /# --8<-- [end:tutorial]/,$d' /tmp/DetectMateService/container/fluentin/fluent.conf
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo
echo "The Nginx access.log will be mounted into the fluentin container and fluentd is using the correct file. We can finally look into the DetectMate config and generate anomalies."