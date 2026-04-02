# ~/.cshrc — Non-root user (csh/tcsh)

# 1. Add ~/bin to PATH
setenv PATH "${HOME}/bin:${HOME}/scripts:${PATH}"

# 2. Source script.csh
if ( -f ${HOME}/scripts/script.csh ) then
    source ${HOME}/scripts/script.csh
endif

# 3. Aliases
alias ll 'ls -alF'
alias .. 'cd ..'
