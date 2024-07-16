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