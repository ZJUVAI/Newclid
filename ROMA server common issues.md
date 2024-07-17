# ROMA server common issues
## Install ssh
[Install ssh as client](https://code.visualstudio.com/docs/remote/troubleshooting#_installing-a-supported-ssh-client)

[Install ssh as server](https://code.visualstudio.com/docs/remote/troubleshooting#_installing-a-supported-ssh-server)

Extension of vscode : ssh fs
## Connection and configuration

### On the client:

(using ed25519 encryption, not necessary)

[Generate a ssh key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)

Example of `"your home dir"/.ssh/config`
```
Host Roma213
    HostName 10.199.195.21
    User "username"
    IdentityFile "your home dir"/.ssh/id_ed25519
```

### On the server:

700 file mode for `.ssh`, 600 for `.ssh/authorized_keys`

In `.ssh/authorized_keys`, append the content of your public key (e.g. `"your home dir"/.ssh/id_ed25519.pub`)

`vi /etc/ssh/sshd_config` to config, some important options:
- `PermitRootLogin yes`
- `PubkeyAuthentication yes`
- `LogLevel DEBUG` or `LogLevel INFO`
- (security issues) `PasswordAuthentication yes`
- `AuthorizedKeysFile .ssh/authorized_keys`

After each change of config: `sudo systemctl restart sshd` to restart the ssh service

To see the ssh log: `sudo systemctl status sshd`

Add user : `sudo adduser username`, switch user : `su - username`, add user to sudoers : `usermod -aG sudo username`.

## Proxy settings

[ref](https://3ms.huawei.com/hi/group/3942456/wiki_6984538.html)
Didn't work for me:/

## DNS settings

`/etc/resolv.conf`

```
options attempts:1
options timeout:1
search huawei.com
nameserver 7.182.30.38
nameserver 7.182.30.40
nameserver 7.221.190.197
```

## Huawei apt source list

to be put in `/etc/apt/source.list`

```
# See http://help.ubuntu.com/community/UpgradeNotes for how to upgrade to
# newer versions of the distribution.
deb http://mirrors.tools.huawei.com/ubuntu focal main restricted
# deb-src http://mirrors.tools.huawei.com/ubuntu focal main restricted

## Major bug fix updates produced after the final release of the
## distribution.
deb http://mirrors.tools.huawei.com/ubuntu focal-updates main restricted
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-updates main restricted

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team. Also, please note that software in universe WILL NOT receive any
## review or updates from the Ubuntu security team.
deb http://mirrors.tools.huawei.com/ubuntu focal universe
# deb-src http://mirrors.tools.huawei.com/ubuntu focal universe
deb http://mirrors.tools.huawei.com/ubuntu focal-updates universe
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-updates universe

## N.B. software from this repository is ENTIRELY UNSUPPORTED by the Ubuntu
## team, and may not be under a free licence. Please satisfy yourself as to
## your rights to use the software. Also, please note that software in
## multiverse WILL NOT receive any review or updates from the Ubuntu
## security team.
deb http://mirrors.tools.huawei.com/ubuntu focal multiverse
# deb-src http://mirrors.tools.huawei.com/ubuntu focal multiverse
deb http://mirrors.tools.huawei.com/ubuntu focal-updates multiverse
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-updates multiverse

## N.B. software from this repository may not have been tested as
## extensively as that contained in the main release, although it includes
## newer versions of some applications which may provide useful features.
## Also, please note that software in backports WILL NOT receive any review
## or updates from the Ubuntu security team.
deb http://mirrors.tools.huawei.com/ubuntu focal-backports main restricted universe multiverse
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-backports main restricted universe multiverse

## Uncomment the following two lines to add software from Canonical's
## 'partner' repository.
## This software is not part of Ubuntu, but is offered by Canonical and the
## respective vendors as a service to Ubuntu users.
# deb http://archive.canonical.com/ubuntu focal partner
# deb-src http://archive.canonical.com/ubuntu focal partner

deb http://mirrors.tools.huawei.com/ubuntu focal-security main restricted
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-security main restricted
deb http://mirrors.tools.huawei.com/ubuntu focal-security universe
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-security universe
deb http://mirrors.tools.huawei.com/ubuntu focal-security multiverse
# deb-src http://mirrors.tools.huawei.com/ubuntu focal-security multiverse
```

## Huawei pip source
```
pip config set global.index-url http://mirrors.tools.huawei.com/pypi/simple
pip config set global.trusted-host "mirrors.tools.huawei.com rnd-gitlab-eu.huawei.com pypi.org files.pythonhosted.org"
```