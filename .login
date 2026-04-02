# ~/.login (only executed when logging in with csh/tcsh)

# Reload .cshrc to ensure the environment is fully set up
if ( -f ~/.cshrc ) then
    source ~/.cshrc
endif

# === Source script.csh at login ===
if ( -f /opt/app/setup/script.csh ) then
    source /opt/app/setup/script.csh
endif

# === Set login-specific environment ===
setenv DISPLAY :0.0
umask 022
