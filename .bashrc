# ~/.bashrc

# === Default RHEL settings (keep as is) ===
# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# === SOURCE SCRIPT.SH ===
# Method 1: Source directly (environment variables and aliases
# will be imported into the current shell)
if [ -f /path/to/script.sh ]; then
    source /path/to/script.sh
    # or equivalently:
    # . /path/to/script.sh
fi

# === RUN SCRIPT.CSH FROM BASH (workaround) ===
# Bash CANNOT directly source .csh files, so we must use a csh subshell

# Method 1: Run script.csh as a subprocess (does NOT import env vars)
alias run_csh_script='csh /path/to/script.csh'

# Method 2: Use a function to "bridge" env vars from csh to bash (advanced)
source_csh() {
    # Run csh, source the .csh file, then export env vars into bash
    eval $(csh -c "source $1 && env" 2>/dev/null | \
        grep -v "^[^=]*=[^=]" | \
        awk -F= '/^[A-Z_][A-Z0-9_]*=/{printf "export %s=\"%s\"\n", $1, $2}')
}

# === PATH CONFIGURATION (if needed) ===
export PATH=$PATH:/path/to/your/scripts

# === USEFUL ALIASES ===
alias ll='ls -alF'
alias grep='grep --color=auto'
