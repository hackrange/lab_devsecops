# A golden image template from another team.  It passes `packer validate`.
# Find at least five problems before it ships.  Author: Tim Rice
packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 0.0.1"
    }
  }
}

source "amazon-ebs" "web" {
  region        = "us-east-1"
  instance_type = "t3.micro"
  ssh_username  = "admin"
  ami_name      = "web-golden-latest"
  source_ami_filter {
    filters = {
      name = "debian-13-amd64-*"
    }
    owners      = ["*"]
    most_recent = true
  }
}

build {
  sources = ["source.amazon-ebs.web"]

  provisioner "file" {
    content     = "[default]\naws_access_key_id = LAB_SECRET_key_id\naws_secret_access_key = LAB_SECRET_access_key\n"
    destination = "/home/admin/.aws/credentials"
  }

  provisioner "shell" {
    inline = [
      "curl -fsSL https://example.com/install-agent.sh | sudo bash",
      "echo 'DB_PASSWORD=LAB_SECRET_db_password' | sudo tee -a /etc/environment"
    ]
  }
}
