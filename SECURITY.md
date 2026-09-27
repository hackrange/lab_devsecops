# Security

This repository is a **cyber security training lab**.  It contains deliberately
vulnerable code, images and configurations, and fake secrets, all for students
to find and fix.  Install it only in a disposable virtual machine on a private
network.

## Planted secrets are not vulnerabilities

This lab teaches secret scanning, so it contains deliberately fake credentials
(a made-up GitHub token, `LAB_SECRET_...` values, sample database passwords,
an example SSH key).  They are listed in the README under "Deliberately fake
secrets".  None of them is real or grants access to anything.

## Reporting a real problem

If you find a real vulnerability in the installer, the lab services or the
control panel, please report it privately: use **Security > Report a
vulnerability** on this repository's GitHub page.  Please do not open a public
issue for a security problem.

The Local Lab is meant to run on a private virtual machine for one student.
Its services only answer on private network addresses, and it should never be
exposed to the internet.

Author: Tim Rice
