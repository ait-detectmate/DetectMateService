#!/bin/bash

year=$(date +%Y)

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
  echo
  if $AUTO_YES; then
    answer="y"
  else
    read -p "Continue? [y/n] " answer
    echo
  fi
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

sudo rm -rf /tmp/DetectMateService

echo "In this tutorial we want to find anomalies in nginx access.logs. So let's install nginx."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
sudo apt update && sudo apt install nginx -y
sudo touch /var/log/nginx/access.log
sudo mv /var/log/nginx/access.log /var/log/nginx/access.log.bac
sudo touch /var/log/nginx/access.log
sudo systemctl restart nginx.service > /dev/null

echo
echo "Send HTTP-request to our local nginx (curl http://localhost)."
echo
curl http://localhost
echo

echo "Now we should have at least one line in /var/log/nginx/access.log."
echo
sudo cat /var/log/nginx/access.log
echo

echo "We need Docker and Docker Compose for the deployment. A comprehensive tutorial about how to install Docker can be found at https://docs.docker.com/engine/install/ubuntu/"
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "First run the following command to uninstall all conflicting packages."
echo
echo "sudo apt remove \$(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc | cut -f1)"
echo
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc | cut -f1)
echo
echo "Now set up Docker's apt repository."
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

echo "With Docker compose working, we will now download the DetectmateService repository using git."
echo "cd /tmp && git clone https://github.com/ait-detectmate/DetectMateService.git && cd DetectMateService"
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
cd /tmp && git clone https://github.com/ait-detectmate/DetectMateService.git && cd DetectMateService

echo
echo "Let's start the default pipeline, just to test it."
echo "sudo docker compose up -d"
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
sudo docker compose up -d
echo
echo "To check the status of the containers, we can use docker compose ps."
echo
sudo docker compose ps
echo
echo "Notice that the pipeline has **two** detector services running side by side: detector (running NewValueDetector) and detector-rule (running RuleDetector). The parser sends every parsed log line to both, and fluentout writes each detector's alerts to its own output file (output.%Y%m%d and output-rule.%Y%m%d)."
echo
echo "For now, we will shutdown all containers."
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "sudo docker compose down -v"
echo
sudo docker compose down -v
echo

echo "We have finally all requirements installed and have a boilerplate template for docker compose that starts an initial pipeline. In the next sections we will reconfigure that pipeline so that we can read the access.log and generate anomalies."
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo "The preconfigured pipeline reads logs from container/fluentlogs/some.log. In order to be able to read the nginx access.log file, we need to mount /var/log/nginx into the fluentin container and modify the fluentd config so that it reads access.log instead."
echo "Initially we edit the docker-compose.yml and change only the fluentin volume mount to use /var/log/nginx."
echo
cat /tmp/DetectMateService/docker-compose.yml
echo
echo "Now that the access.logs are available in the container, we have to point fluentd to read that file. We need to edit the file container/fluentin/fluent.conf and replace path /fluentd/log/some.log with path /fluentd/log/access.log."
echo "sed -i 's|/fluentd/log/some\.log|/fluentd/log/access.log|g' /tmp/DetectMateService/container/fluentin/fluent.conf"
echo
sed -i 's|/fluentd/log/some\.log|/fluentd/log/access.log|g' /tmp/DetectMateService/container/fluentin/fluent.conf
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "The Nginx access.log will be mounted into the fluentin container and fluentd is using the correct file. We can finally look into the DetectMate config and generate anomalies."
echo

echo "DetectMate Config"
echo
echo "The log pipeline uses three DetectMate services: parser, detector and detector-rule. The parser splits the log line into meaningful tokens, which the two detectors then use to identify anomalies, each with a different strategy. We need to configure the parser and both detectors. Since the detectors need to know which tokens they receive from the parser so they can look for anomalies, all three configurations are closely related."
echo
echo "Next we will configure the parsers."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "Parser"
echo
echo "The Nginx log line we previously created has a very specific format:"
echo '::1 - - [18/Mar/2026:11:43:30 +0000] "GET / HTTP/1.1" 200 615 "-" "curl/8.5.0"'
echo
echo "This format can be described with the following template:"
echo '<IP> - - [<Time>] "<Method> <URL> <Protocol>" <Status> <Bytes> "<Referer>" "<UserAgent>"'
echo
echo "DetectMate includes a matcher_parser that can split such a log line. The configuration for the parser is stored at container/config/parser_config.yaml."
echo
cat container/config/parser_config.yaml
echo
echo "container/config/templates.txt contains a single wildcard template that matches any well-formed access-log line:"
echo
cat container/config/templates.txt
echo
echo "This means every normal Nginx request parses successfully. We will rely on this later: a log line that does not match this template is exactly what the rule-based detector's TemplateNotFound rule reacts to. We don't need to modify the parser configuration otherwise, since it is already compatible with the nginx access.log format. We can now continue with the configuration of the detectors."
echo
echo "Next we will configure the detectors."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "Detector"
echo
echo "The simplest way to generate anomalies is to watch a single field of the parsed data and learn all its values during training. As soon as the detector switches from training mode to detection mode, all values not found in the trained model are flagged as anomalies. DetectMate ships with a new_value_detector that can do exactly that. The config container/config/detector_config.yaml looks as follows:"
echo
cat container/config/detector_config.yaml
echo
echo "Here, the URL token from the parsed data is monitored (- pos: URL), and the first two log lines are used for training (data_use_training: 2). Any subsequent log lines will be evaluated for anomalies and compared against the values seen during training on the first two log lines."
echo
echo "Next we will configure the rule-based detector."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "Rule-Based Detector"
echo
echo "Next to the NewValueDetector, the pipeline also runs a second detector, detector-rule, using the rule_detector method. Unlike NewValueDetector, it needs no training: it evaluates a fixed list of simple rules against every log line, such as \"no template was found by the parser\" or \"the log text contains a keyword like 'error' or 'exception'\". Its configuration is stored in container/config/detector_rule_config.yaml:"
echo
cat container/config/detector_rule_config.yaml
echo
echo "By default (when nothing is specified in the rule: block), R001, R003 and R004 are enabled."
echo "With the config above only 'R003' and 'R004' are enabled, so the rule-based detector stays quiet while we work through the rest of this tutorial (plain Nginx access logs don't contain exception/error keywords, nor a 'Level' field). At the very end of this tutorial, we will enable the 'R001 - TemplateNotFound' rule and deliberately send a log line that cannot be parsed, to see the rule-based detector raise its own alert."
echo
echo "Now let's start the pipeline using sudo docker compose up -d and send two valid log lines with two different status values."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "sudo docker compose up -d"
echo
sudo docker compose up -d
echo
echo "sudo docker compose ps"
echo
sudo docker compose ps
echo
echo "Wait a couple of minutes until parser and detector containers are up and running. You can check by executing sudo docker compose logs parser, sudo docker compose logs detector or sudo docker compose logs detector-rule."
echo "When the containers are ready, the output of the component will show Uvicorn running on or any HTTP-requests for the /metrics endpoint."
while true; do
  echo "Waiting for services to boot up.."
  sleep 5
  sudo docker compose logs parser | grep "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)" > /dev/null
  if [ $? -ne 0 ]; then continue; fi
  sudo docker compose logs detector | grep "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)" > /dev/null
  if [ $? -ne 0 ]; then continue; fi
  sudo docker compose logs detector-rule | grep "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)" > /dev/null
  if [ $? -ne 0 ]; then continue; fi
  sleep 60
  echo "Services started up successfully."
  echo
  break
done

if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "Now generate two access.log lines using curl http://localhost/hello and curl http://localhost/world."
echo
echo "curl http://localhost/hello"
curl http://localhost/hello
sleep 1
echo
echo "curl http://localhost/world"
curl http://localhost/world
sleep 1
echo
echo "We now trained with the two values hello and world. This means, as soon as we query any other url than /hello or /world we should receive an anomaly. Anomalies get logged in container/fluentlogs/output.%Y%m%d. With ls container/fluentlogs/output.%Y%m%d find the filename output.<date>.log and have a look:"
echo
echo "Create Anomaly using curl http://localhost/foobar."
curl http://localhost/foobar
sleep 1
echo
echo "Great! We detected our first anomaly."
echo
file=$(echo /tmp/DetectMateService/container/fluentlogs/output.$year*.log)
echo "cat $file"
cat "$file"
echo
echo "If you check container/fluentlogs/output-rule.%Y%m%d at this point, you'll find it empty (or missing entirely). The rule-based detector has stayed quiet the whole time, since none of the requests we sent contain an exception/error keyword. We'll change that in the next part."
echo
echo "Triggering the Rule-Based Detector"
echo
echo "So far, detector-rule has been running quietly next to detector, since none of our requests matched any of its enabled rules. To see it raise an alert, we'll enable the R001 - TemplateNotFound rule and then generate a log line that the parser cannot match against the template in container/config/templates.txt."
echo "Edit container/config/detector_rule_config.yaml and add the rule \"R001 - TemplateNotFound\":"
echo
echo "sed -i '/R001 - TemplateNotFound/s/# - rule/- rule/' container/config/detector_rule_config.yaml"
sed -i '/R001 - TemplateNotFound/s/# - rule/- rule/' container/config/detector_rule_config.yaml
echo
echo "cat container/config/detector_rule_config.yaml"
cat container/config/detector_rule_config.yaml
echo
echo "Now we will restart just the detector-rule service to pick up the change."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo "sudo docker compose restart detector-rule"
sudo docker compose restart detector-rule
restart_time=$(date --iso-8601=seconds)

while true; do
  echo "Waiting for service to boot up.."
  sleep 5
  sudo docker compose logs --since "$restart_time" detector-rule | grep "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)" > /dev/null
  if [ $? -ne 0 ]; then continue; fi
  sleep 60
  echo "Services started up successfully."
  echo
  break
done

echo "Now append a contrived log line to /var/log/nginx/access.log that doesn't match the Nginx access log template at all, for example a line without the expected quotes and brackets."
echo "echo 'this line does not match the configured nginx log format at all' | sudo tee -a /var/log/nginx/access.log"
echo 'this line does not match the configured nginx log format at all' | sudo tee -a /var/log/nginx/access.log
sleep 1
echo
echo "Since this line can't be matched against <*> - - [<*>] \"<*> <*> <*>\" <*> <*> \"<*>\" \"<*>\", the parser assigns it EventID: -1, which is exactly what the TemplateNotFound rule checks for. Have a look at container/fluentlogs/output-rule.%Y%m%d."
echo
file=$(echo /tmp/DetectMateService/container/fluentlogs/output-rule.$year*.log)
echo "cat $file"
cat "$file"
echo
echo "The rule-based detector caught it: \"R001 - TemplateNotFound\":\"No template found by parser\". Unlike NewValueDetector, it needed no training data at all — it was ready to alert from the very first log line."
echo
echo "Grafana UI"
echo
echo 'The Grafana UI is accessible at http://localhost:3000 (default login credentials in this demo are admin/admin) and the raw Prometheus metrics can be explored under "Drilldown" → "Metrics". Under "Dashboards" is a basic Dashboard with graphs for Throughput, Latency, Processing rate and Engine state.'
echo
echo "This was a very basic example, but it shows how to easily deploy a full log data anomaly pipeline, including two different DetectMate detectors, using a parser for the Nginx access log format, and how this is then used to flag anomalies."
echo

echo "Shutdown all containers."
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
echo "sudo docker compose down -v"
echo
sudo docker compose down -v
echo

sudo rm /var/log/nginx/access.log
sudo mv /var/log/nginx/access.log.bac /var/log/nginx/access.log

echo "Remove temporary stuff from docker using 'sudo docker container prune -f', 'sudo docker image prune -f', and 'docker system prune -f'."
echo
if $AUTO_YES; then
  answer="y"
else
  read -p "Continue? [y/n] " answer
  echo
fi
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
sudo docker container prune -f
sudo docker image prune -f
sudo docker system prune -f
