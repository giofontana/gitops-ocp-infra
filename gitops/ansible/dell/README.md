
# Prepare Ansible EE image to use Idrac

Pre-req: Run from a RHEL 9 server registered with subscription manager

sudo dnf install python3-pip
python3 -m pip install ansible-builder --user

mkdir idrac_ee && cd idrac_ee

```bash
cat <<EOF > execution-environment.yml
version: 3

images:
  base_image: 
    name: 'registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest'

dependencies:
  galaxy:
    collections:
      - name: 'dellemc.openmanage'

options:
  package_manager_path: '/usr/bin/microdnf'

EOF

ansible-builder build --tag <aap-automation-hub>/admin/ee-idrac-rhel-9
podman login <aap-automation-hub> --tls-verify=false
podman push <aap-automation-hub>/admin/ee-idrac-rhel-9 --tls-verify=false

```
