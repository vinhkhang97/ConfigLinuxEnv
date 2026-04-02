# ~/.bash_profile

# === Load all configurations from .bashrc ===
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# === Environment variables that only need to be set once at login ===
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk
export ORACLE_HOME=/u01/app/oracle/product/19c
export PATH=$PATH:$HOME/bin:$JAVA_HOME/bin

# === Source script.sh at login (if not already sourced in .bashrc) ===
if [ -f /opt/app/setup/script.sh ]; then
    source /opt/app/setup/script.sh
fi
