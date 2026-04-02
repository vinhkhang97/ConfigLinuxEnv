# ~/.bashrc — Non-root user

# 1. Load system-wide configuration (keep this line unchanged)
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# 2. Add ~/bin to PATH so personal scripts can run without full path
export PATH=$HOME/bin:$HOME/scripts:$PATH

# 3. Source your script.sh (runs in the current shell)
if [ -f $HOME/scripts/script.sh ]; then
    source $HOME/scripts/script.sh
fi

# 4. Useful aliases
alias ll='ls -alF'
alias ..='cd ..'
