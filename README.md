# HackRange DevSecOps Cyber Security Training Lab

> **This is a cyber security training lab, not software to run in production.**
>
> It builds a self-contained practice environment, the "Local Lab" option for
> the HackRange course [*Learning the Software Build Process: A Four-Week
> DevSecOps Intensive*](https://lms.hackrange.com/courses/view.php?c=8e09034afcde8ab12ca677a112846332).  On
> purpose, it contains:
>
> - **fake secrets** (tokens, passwords, keys) planted for students to find with
>   secret scanners (see [Deliberately fake secrets](#deliberately-fake-secrets-read-this-before-you-report-a-leak));
> - **deliberately vulnerable code, images and configurations** that students
>   attack, scan, and then fix;
> - lab services with **training defaults**, meant for one student on a private
>   virtual machine.
>
> Install it only inside a **disposable virtual machine on a private network**.
> Never on a server, never on a machine you care about, and never where the
> internet can reach it.

This lab is the **"Local Lab" option** for the HackRange course
[**Learning the Software Build Process: A Four-Week DevSecOps Intensive**](https://lms.hackrange.com/courses/view.php?c=8e09034afcde8ab12ca677a112846332).
The course runs its labs for you in the browser.  The Local Lab lets students
**host their own lab locally**, on their own computer, in a virtual machine
running **Ubuntu 22.04 or newer** (22.04, 24.04, and later releases, on Intel,
AMD or ARM processors, including Apple Silicon Macs).  One command installs
everything the course's labs need.

**New to virtual machines or the command line?**  Read
[**Documentation.pdf**](https://raw.githubusercontent.com/hackrange/lab_devsecops/main/Documentation.pdf) (the link downloads it) first.  It walks you through every
step with screenshots: creating the Ubuntu virtual machine, running the
installer, signing in to your lab, and removing it when the course ends.
It assumes no technical background.

The Local Lab gives you the same workstation, the same tools and the same lab
services as the hosted labs: the lab Git server with its CI runner, the
package registry, the SAST platform, and your own Kubernetes cluster.  The
lessons' commands work unchanged.

## Install it (one command)

In a terminal **inside your Ubuntu virtual machine**, run:

```bash
curl -fsSL https://raw.githubusercontent.com/hackrange/lab_devsecops/main/install.sh | sudo bash
```

That's it.  The installer checks your machine, installs everything the labs
need (including Docker), builds the lab, and starts your first lab session.
The first install takes **30 to 90 minutes**, mostly downloading and building,
and downloads about **20 GB**.  You can leave it running.

If it stops for any reason, fix what it tells you and **run the same command
again**.  It picks up where it left off.

When it finishes, it shows you **how to get into your lab**: a web address
to open in your browser, a username (`student`) and a password.  Write them
down somewhere private, or just run this any time to see them again:

```bash
/opt/hackrange-labs/show_information.sh
```

Then log out of Ubuntu and back in once, so the lab commands work without
typing `sudo`.

## Hardware requirements

The lab runs inside **one Ubuntu virtual machine (VM)**.  Give that VM at
least the minimum below.  More is better, especially on the Kubernetes days
(Weeks 3 and 4).

| For the virtual machine | Minimum | Recommended |
|---|---|---|
| Processor type | 64-bit Intel/AMD (x86_64) **or** ARM64 (Apple Silicon M1 or newer, other ARM64) | same |
| Processor cores (vCPUs) | 4 | 8 or more |
| Memory (RAM) | 16 GB | 24 GB or more |
| Virtual disk | 120 GB (100 GB free after Ubuntu) | 160 GB or more, on an SSD |
| Operating system | Ubuntu 22.04 LTS or newer | Ubuntu 24.04 LTS **Desktop** |
| Network | Internet access (NAT networking is best) | same |
| Screen | Any; a desktop lets you open the lab with one command | Ubuntu Desktop at 1920x1080 |

**Your own computer needs more than the VM**, because it runs its own system
too:

| Your computer | Minimum | Recommended |
|---|---|---|
| Memory | 24 GB (so the VM can have 16 GB) | 32 GB or more |
| Free disk | 150 GB | 200 GB or more, SSD |
| Processor | 6 cores, hardware virtualization on (Intel VT-x, AMD-V, or any Apple Silicon Mac) | 8 cores or more |

Hardware virtualization must be turned on in your computer's BIOS/UEFI
settings (it usually already is).  **Nested virtualization is not needed.**

A Mac with Apple Silicon and 16 GB of memory cannot give a VM 16 GB.  Use a
computer with more memory, or use the hosted labs in the course instead.

### Where the resources go

These numbers are measured from the lab itself, not guessed.

| Part of the lab | Disk | Memory while in use |
|---|---|---|
| Lab workstation (all course tools, desktop, Firefox, VS Code) | 16 GB | 2 to 4 GB (scanners peak around 1.5 GB) |
| Build space during the first install (freed afterward) | about 15 GB | about 4 GB |
| SAST platform (Git Code Review) | 2.5 GB | 1 to 2 GB while scanning |
| Package registry (ForgeRepo) and its cache | 1 GB, growing to about 10 GB over the course | about 1 GB |
| Lab Git server (Forgejo) and CI jobs | 2 GB | 1 to 2 GB while a pipeline runs |
| Kubernetes and your cluster (Weeks 3 and 4) | 6 to 8 GB | 3 to 4 GB |
| Ubuntu itself | 10 to 15 GB | 2 GB |

## Before you install: create the virtual machine

Pick the section for the computer you have.  Give the VM the sizes from the
table above, and install Ubuntu 24.04 with the default options.

**Windows (Intel or AMD):** install
[VirtualBox](https://www.virtualbox.org/) (free),
VMware Workstation Pro (free for personal use), or turn on Hyper-V.  Download
the Ubuntu 24.04 Desktop ISO from
[ubuntu.com/download/desktop](https://ubuntu.com/download/desktop), create a
new VM from it, and install.  Do not use WSL: it cannot run the lab.

**Mac with Apple Silicon (M1, M2, M3, M4 or newer):** install
[UTM](https://mac.getutm.app/) (free), VMware Fusion (free for personal use),
or Parallels.  You need the **ARM64** edition of Ubuntu:
download Ubuntu Server for ARM from
[ubuntu.com/download/server/arm](https://ubuntu.com/download/server/arm),
install it, then add a desktop with
`sudo apt install ubuntu-desktop-minimal` and restart.  (UTM's gallery and
Parallels also offer ready-made Ubuntu ARM64 desktop VMs.)  The installer
detects ARM automatically.

**Mac with Intel:** VMware Fusion, Parallels, or VirtualBox, with the normal
Ubuntu 24.04 Desktop ISO.

**Linux:** use virt-manager (KVM), VirtualBox or VMware with the Ubuntu 24.04
Desktop ISO.

Running the installer on a Mac itself (outside a VM) stops with these same
instructions.

## Getting into your lab

Open the web address the installer showed you, in the web browser on **your
own computer** (or in the Ubuntu VM itself).  It looks like this:

```
https://192.168.64.5:8446
```

Sign in with username **`student`** and the password.  The lab desktop opens
right in your browser, the same as the hosted labs in the course.

**The lab services, from inside the lab and from your own computer.**  The
lessons use names that only exist inside the lab.  From your own computer,
use the VM's address instead (the same one as the web desktop):

| Service | Inside the lab (as the lessons say) | From your own computer |
|---|---|---|
| Git server (Forgejo) | `https://labgit.lab:8444` | `https://<VM address>:8444` |
| Package registry portal | `https://labrepo.lab:8443/admin/` | `https://<VM address>:8443/admin/` |
| Code review (Git Code Review) | `https://10.10.10.70:8445` | `https://<VM address>:8445` |
| Keycloak (admin console) | `https://10.10.10.70:8448` | `https://<VM address>:8448` |
| Kong Manager | `https://10.10.10.70:8449` | inside the lab only (it has no login) |
| Kong gateway | `https://10.10.10.70:8451` | `https://<VM address>:8451` |
| Grafana (Loki and Tempo connected) | `https://10.10.10.70:8452` | `https://<VM address>:8452` |

`show_information.sh` prints them with your VM's real address filled in, and
`hackrange-lab env` shows the username and password for each.  Like the web
desktop, they answer only computers on your own private network.

The same username and password also work for SSH (see
[Connecting with SSH](#connecting-with-ssh-a-step-by-step-guide)) and for any
Remote Desktop app.

**The password changes every time you start a fresh lab session**
(`hackrange-lab start` after a stop, or `hackrange-lab reset`) and after every
install or update.  That is on purpose: if the password ever leaks, it stops
working the next time you start fresh.  To see the current one:

```bash
/opt/hackrange-labs/show_information.sh
```

It may ask for your **Ubuntu password** first (the one you log in to Ubuntu
with), because the lab password is kept where only an administrator can read
it.

### Your lab control panel

The lab desktop's Firefox opens on your **lab control panel**.  From your own
computer it is at `https://<VM address>:8446/control/` (sign in with the same
username and password).  It shows:

- **How hard the lab is working:** processor, memory and disk for the whole
  VM, and the processor and memory each part of the lab is using.
- **Every lab service** with its address, username and password (with Copy
  buttons), and the live two-step code for Git Code Review.
- **Start and Stop buttons** for the Git server, the package registry, Git
  Code Review, Keycloak, Kong, Grafana (with Loki and Tempo), your Kubernetes
  cluster, and the copies of Keycloak, Kong and Grafana your Week 4 lessons
  install in your cluster.  Stop what you are not using to free up memory;
  everything starts again on its own when the VM restarts.
- **Reset to default** on each service: if you break something, it deletes
  what you made in that service and puts it back the way a fresh install left
  it (with a fresh account where it has one).  Resetting the Git server also
  resets Git Code Review, which scans it.
- **Start over**: one button, at the bottom, that resets the whole lab.  Type
  `RESET` to confirm.  It takes a few minutes, not a reinstall.

Keycloak, Kong and Grafana (with Loki and Tempo) are always running, with
their logins on the panel.  Your Week 4 lessons also have you install your
own copies inside your Kubernetes cluster; those are separate, and the lesson
steps work exactly as written.

Nothing in the lab times out: your lab session keeps running, and comes back
after a restart of the VM, until you stop it.

### Staying safe (please read this once)

- **The browser warning.**  The first time you open the lab, your browser
  says something like *Your connection is not private*.  That is because the
  lab uses its own certificate, one your browser has never seen.  For **this
  lab address only**, click **Advanced** and then **Continue** (or **Accept
  the risk**).  Never do that for a bank, email or shopping site, where that
  warning can mean someone is intercepting you.  To make the warning go away
  for good, see [Trust your lab's certificate](#optional-trust-your-labs-certificate).
- **Keep the password to yourself.**  Do not paste it into a chat, a forum or
  a screenshot you share.  If you think someone saw it, push your work and run
  `hackrange-lab reset`: you get a new one.
- **The lab only answers computers on your own private network** (your home
  or office network, or your computer talking to its own VM).  It refuses
  anything from the internet, even with the right password.  **Do not forward
  these ports on your router**, and do not put this VM on a public cloud
  server.
- If the Ubuntu VM itself sits directly on the internet (a cloud server), the
  lab will not answer your own computer at all.  Open it from inside the VM
  instead, or ask your instructor about an SSH tunnel.

### Your VM's network settings

Your own computer has to be able to reach the VM.  With the default settings:

- **VMware (Workstation, Fusion), Parallels, UTM:** works as it is (NAT or
  Shared network).
- **VirtualBox:** its default NAT network hides the VM from your computer.
  Shut the VM down, open **Settings → Network → Adapter 2**, tick **Enable
  Network Adapter**, choose **Host-only Adapter**, and start the VM again.
  Then run `show_information.sh`: it shows the new address.  (Host-only means
  only your own computer can reach the VM, which is exactly what you want.)
- **Hyper-V:** the **Default Switch** works as it is.

If the web address does not open, try the address from inside the Ubuntu VM
first (`https://127.0.0.1:8446`).  If that works, the problem is the VM's
network setting above.

### Optional: trust your lab's certificate

This makes the browser warning disappear, and it is how real companies handle
their own private certificates.

1. On your own computer, open `https://<your lab address>:8446/lab-ca.crt`
   (accept the warning one last time).  It downloads a file called
   `lab-ca.crt`.  It is public: it proves the lab is yours, and holds no
   secret.
2. **Check that it really is your lab's certificate.**  In the Ubuntu
   machine, run `./show_information.sh` (or `hackrange-lab info`): near the
   end it prints the certificate's **fingerprint**, a long line of letters and
   numbers in pairs.  On your own computer, open the downloaded file (Windows
   and Mac show a **SHA-256** fingerprint on its details page) and compare.
   If they are not identical, delete the file and do not go on: something
   between your computer and the lab changed it.
3. Add it as a trusted certificate:
   - **Windows:** double-click the file, **Install Certificate**, **Current
     User**, **Place all certificates in the following store**, **Browse**,
     **Trusted Root Certification Authorities**, **OK**, **Finish**.
   - **Mac:** double-click the file (it opens Keychain Access and adds it to
     **login**).  Then double-click the certificate in the list, open
     **Trust**, set **When using this certificate** to **Always Trust**, and
     close the window.
   - **Firefox** (any system) keeps its own list: **Settings**, search for
     **certificates**, **View Certificates**, **Authorities**, **Import**,
     choose the file, tick **Trust this CA to identify websites**.
4. Close and reopen the browser.

The certificate belongs to this one lab.  If you uninstall and reinstall the
lab, it makes a new one, and you repeat these steps.  It is limited on
purpose: it can vouch only for the lab's own names and for private network
addresses, never for a real website.

**When you finish the course, remove it** (the same place you added it):
**Windows:** run `certmgr.msc`, open **Trusted Root Certification
Authorities**, **Certificates**, right-click **Hackrange Local Lab CA**,
**Delete**.  **Mac:** Keychain Access, **login**, find **Hackrange Local Lab
CA**, **Delete**.  **Firefox:** **View Certificates**, **Authorities**, select
it, **Delete or Distrust**.

## Using the lab

In the course, each lab says to launch the lab.  With the Local Lab, you run
these instead:

| Command | What it does |
|---|---|
| `/opt/hackrange-labs/show_information.sh` | Shows the web address, the username and the current password |
| `hackrange-lab info` | The same, as a lab command |
| `hackrange-lab desktop` | Opens the lab desktop in a window on the Ubuntu VM |
| `hackrange-lab start` | Starts a fresh lab session (with a new password) and shows how to connect |
| `hackrange-lab shell` | A terminal inside the lab session (no password needed) |
| `hackrange-lab ssh` | Connects to the lab session with SSH, showing the password first |
| `hackrange-lab env` | Your lab URLs, usernames, passwords and tokens |
| `hackrange-lab totp` | The current two-step code for Git Code Review |
| `hackrange-lab stop` | Ends the session (the workstation is deleted) |
| `hackrange-lab reset` | Ends the session and starts a fresh one, with a new password |
| `hackrange-lab status` | Checks that every part of the lab is running |
| `hackrange-lab update` | Gets the latest version of the lab |
| `hackrange-lab diag` | Saves a diagnostics file (passwords and tokens removed) to send when you need help |

The applications menu also has a **Hackrange Lab** icon that opens the
desktop.

**A lab session works like the hosted lab.**  The workstation is disposable:
each lab starts from a fresh one, and your work lives on the lab Git server.
Push before you run `hackrange-lab stop`.  Your repositories, your package
registry account, your findings and your Kubernetes cluster are **not**
touched by `stop` or `reset`; they keep running in the background, and they
come back after a reboot on their own.

When the lab desktop opens, Firefox shows **Your Local Lab**: every lab
service with its username and password, and these same ways in.  To see it
again, open Firefox (it is the home page).

### Connecting with SSH (a step by step guide)

SSH is how people work on servers they cannot sit in front of.  You type
commands on your computer, and they run on the other machine.  Many lessons
assume you are comfortable with it, so it is worth learning here.

**1. Open a terminal.**  A terminal is a window where you type commands.

- On your Ubuntu VM: press **Ctrl+Alt+T**.
- On Windows (only if your VM has no desktop): open the Start menu, type
  **PowerShell**, and press Enter.
- On a Mac (only if your VM has no desktop): press **Command+Space**, type
  **Terminal**, and press Enter.

**2. Find your password.**  Type this and press Enter (on the Ubuntu VM):

```bash
/opt/hackrange-labs/show_information.sh
```

It prints the SSH command to use and the current password.  The user is
always `student`.

**3. Connect.**  On the Ubuntu VM, type:

```bash
ssh -p 2222 student@127.0.0.1
```

From your own computer, use the address that `show_information.sh` printed
instead of `127.0.0.1`.

- `-p 2222` is the port: the lab listens for SSH on 2222, not the usual 22.
- `student` is the user, and after the `@` is the machine to connect to.

**4. Answer the first-time question.**  The first time, SSH asks
*Are you sure you want to continue connecting (yes/no)?*  Type `yes` and press
Enter.  It is checking that it is talking to the right machine, and it only
asks once.

**5. Type the password.**  Type the password from step 2 and press Enter.
**Nothing appears on the screen while you type a password**, not even dots.
That is normal: it is still typing.  If you make a mistake, press Enter and
try again.

**6. You are in.**  The prompt changes to `student@devsecops-lab`, and every
command now runs inside the lab.  Type `exit` and press Enter to leave.

**The shortcut:** `hackrange-lab ssh` does steps 2 to 4 for you: it shows the
password and connects.  And `hackrange-lab shell` gets you a lab terminal with
no password at all.

If SSH ever says *Connection refused*, the lab session is not running: type
`hackrange-lab start` and try again.  If it says *Permission denied*, the
password has changed since you last looked: run `show_information.sh` again.

## Keep your lab safe

- **Who can reach it.**  The web desktop (8446), SSH (2222), Remote Desktop
  (13389) and the lab services' outside doors (8443 to 8452) answer only
  *private* network addresses, never the internet.  "Private" still means
  everyone on the same network: at home that is your family's devices, but on
  a school, office or cafe network it can be hundreds of strangers.  On a
  shared network, give the virtual machine a **NAT** or **host-only** network
  (see [Before you install](#before-you-install-create-the-virtual-machine))
  so only your own computer can reach it.
- **Passwords.**  The lab password changes at every new session and every
  install; the other services' passwords are made fresh for each install.
  None of them protects anything but this lab, and none should be reused
  anywhere else.
- **Never expose it to the internet** (no port forwarding on your router, no
  public cloud server).  It is a training lab with training defaults.
- **Apple Silicon and other ARM machines:** the installer turns on
  `vm.legacy_va_layout`, a kernel setting some x86 tools need to run under
  emulation.  It makes memory layout randomization weaker for the whole
  virtual machine, one more reason the lab belongs in a machine of its own.
- When you finish the course, run the uninstaller (below), remove the lab
  certificate if you trusted it, and delete the virtual machine.

## How the Local Lab differs from the hosted labs

Almost nothing, on purpose.  These are the differences you might notice:

- **Open internet.**  The hosted labs only allow a short list of sites.  Your
  Local Lab has normal internet access.  The one lesson where this shows: on
  Day 6, `npm install --registry https://registry.npmjs.org left-pad` is meant
  to be refused by the lab's network filter.  On the Local Lab it succeeds.
  Read the lesson's explanation of why it would fail in a locked-down
  environment.
- **Sessions do not expire.**  A hosted lab closes after four hours.  Yours
  runs until you stop it.
- **You are `student01`.**  That matches the example output in the lessons.
- **Your own certificate authority.**  The lab services use a certificate from
  a private lab CA that the installer created on your VM.  Its key never
  leaves your machine.
- **ARM64 machines** show `arm64` where the lessons' example output shows
  `amd64` (for example in package URLs on Days 8 and 9).  On Days 5 and 20 the
  pipelines download an x86 build of gitleaks on purpose; the installer adds
  x86 emulation so that works, a little slower.

## Updating and removing

Get the latest version of the lab (safe at any time; it never touches a
running session):

```bash
hackrange-lab update
```

Remove the Local Lab and everything in it, including your lab repositories
(Docker itself stays installed):

```bash
sudo /opt/hackrange-labs/uninstall.sh
```

## Troubleshooting

- **The installer stopped.**  Read the message, fix what it says, and run the
  install command again.  The full log is `/var/log/hackrange-install.log`.
- **Asking for help.**  Run `hackrange-lab diag` and send the file it saves.
  It holds the install log, the state of every part of the lab and their
  logs, with every password, token and key removed.
- **"This virtual machine is smaller than the lab needs."**  Shut the VM
  down, give it more memory, cores or disk in your virtualization app, start
  it, and run the install command again.
- **Something stopped working, or after a reboot.**  Run
  `hackrange-lab status`.  Each line that is down shows the command that
  fixes it.
- **The web address does not open on my own computer.**  Try
  `https://127.0.0.1:8446` inside the Ubuntu VM first.  If that works, fix the
  VM's network setting (see [Your VM's network settings](#your-vms-network-settings)).
- **`https://labgit.lab:8444` does not open on my own computer.**  Those names
  only work inside the lab.  On your own computer, use the VM's address:
  `https://<VM address>:8444` (run `show_information.sh` to see it).
- **The password does not work.**  It changes every time a fresh session
  starts.  Run `/opt/hackrange-labs/show_information.sh` to see the current
  one.  After five wrong tries the web desktop makes you wait five minutes.
- **"permission denied" from docker.**  Log out and back in once after the
  install.
- **A lab says a command failed to reach `labgit.lab` or `labrepo.lab`.**
  Run `hackrange-lab status`, then `hackrange-lab reset`.

---

## Deliberately fake secrets (read this before you report a leak)

This repository contains **fake credentials on purpose**.  The course teaches
students to find leaked secrets, so the lab ships repositories, images and
files with secrets planted in them for students to hunt down with tools such
as Gitleaks, TruffleHog and Trivy.  **None of them is real, none has ever been
issued by any service, and none grants access to anything.**  They live under
`images/devsecops-lab/fixtures/` and are used only by the lab exercises:

| What it looks like | Where | Why it is there |
|---|---|---|
| A GitHub personal access token (`ghp_Dq1v...`) | `fixtures/build-leaky-repo.sh` | Day 5: the "leaky repository" whose history students scan.  It was made up for the lab: it fails GitHub's own token checksum and has never existed on GitHub. |
| `LAB_SECRET_...` values (API keys, passwords, session secrets) | `fixtures/build-leaky-repo.sh`, `day04/`, `day05/`, `day09/`, `day10/`, `day12/` | A marker the course uses for every planted secret, so students (and a custom Gitleaks rule they write) can tell a training secret from a real one at a glance. |
| An AWS access key id (`AKIALABFAKE000000001`) | `fixtures/day05/spot-the-bug/deploy.yml` | "Spot the bug": a cloud key hard-coded in a deploy file.  It says FAKE in the id and is not a valid AWS key. |
| Database URLs with passwords (`postgres://app:...`, `postgresql://pawn:...`) | `fixtures/build-leaky-repo.sh`, `fixtures/mystery-repo/Dockerfile`, `fixtures/day05/spot-the-bug/.env` | "Spot the bug" reviews and the leaky repository: a password in a connection string. |
| An "attacker" SSH public key (`...EXAMPLEattackerkey attacker@evil`) | `fixtures/day15/make-incident.sh` | Day 15: the incident Falco detects.  It is a placeholder, not a usable key. |

If a secret scanner (GitHub secret scanning, Gitleaks, TruffleHog) flags any of
these, that is the point of the exercise: please do not report them as leaks.
GitHub's own secret scanning is switched off for this repository, and
`.github/secret_scanning.yml` excludes the fixtures folder for anyone who turns
it back on or forks the repository.
To report a real security problem, see [SECURITY.md](SECURITY.md).

## For maintainers

This repository holds the Local Lab for one course.  Everything the installer does
lives in small numbered steps, each safe to run again:

| Path | What it is |
|---|---|
| `install.sh` | The one-line entry point: checks the machine, fetches this repository to `/opt/hackrange-labs`, runs the steps |
| `scripts/lib.sh` | Shared helpers: output, logging, retries, secrets |
| `scripts/10-preflight.sh` | Size, OS, internet and port checks |
| `scripts/20-packages.sh` | System packages and Docker (Docker's repository, Ubuntu's packages as a fallback) |
| `scripts/30-network.sh` | The lab address `10.10.10.70` on a private `lab0` interface, and the lab hostnames |
| `scripts/40-certs.sh` | This machine's lab CA and the service certificate |
| `scripts/50-images.sh` | Builds the workstation, registry and SAST images for this processor; x86 emulation on ARM |
| `scripts/60-services.sh` | Forgejo, ForgeRepo and Git Code Review (`config/compose.yml`) behind nginx, set up the way the course uses them |
| `scripts/70-kubernetes.sh` | k3s and vcluster, as on the hosted lab node |
| `scripts/80-runner.sh` | The Forgejo Actions runner |
| `scripts/90-student.sh` | The student's accounts and cluster, `hackrange-lab`, the first session |
| `bin/hackrange-access` | The way in: rotates the lab password at every fresh session, keeps the web desktop's certificate matching the VM's addresses, prints the information screen |
| `show_information.sh` | The student's "how do I get in again" script (runs `hackrange-access info`) |
| `config/nginx/hackrange-access.conf`, `hackrange-private-only.conf` | The web desktop on 8446, and the private-networks-only rule for it, SSH (2222) and RDP (13389) |
| `bin/lab_provision.py` | The hosted lab node's provisioner, unchanged, called directly by `bin/hackrange-provision` |
| `bin/seed-lab-registry.sh`, `bin/lab-student-registry.sh`, `bin/forgerepo-lib.sh` | The hosted course's registry scripts, unchanged |
| `bin/lab-vcluster` | The hosted script, listening on the lab address only |
| `images/devsecops-lab*` | The hosted workstation images, made to build for amd64 or arm64 |
| `patches/github-code-review` | The three Git Code Review fixes the hosted labs run, applied to its public source |
| `versions.env` | Every pinned version, in one place |
| `tests/check-downloads.sh` | Proves every workstation download and checksum for `amd64` or `arm64` without building the image |

Differences from the hosted course, all deliberate: one student, so no
containment firewall, no egress allowlist and no network policy between
tenants; the cluster keeps the same quota, limits and Pod Security rules,
because the lessons depend on them.

When the hosted lab images or scripts change, copy the change here and run
`tests/check-downloads.sh amd64` and `tests/check-downloads.sh arm64` if a
download changed.

Author: Tim Rice
