# ~/.cshrc

# === Source script.csh (equivalent to source in bash) ===
if ( -f /path/to/script.csh ) then
    source /path/to/script.csh
endif

# === PATH configuration ===
setenv PATH "${PATH}:/path/to/your/scripts"

# === RUN script.sh FROM csh ===
# csh/tcsh CAN execute .sh files as a subprocess (but cannot source them)
# Run as a subprocess using bash:
alias run_sh 'bash /path/to/script.sh'

# === Common aliases ===
alias ll 'ls -alF'
alias grep 'grep --color=auto'

# === Environment variables ===
setenv JAVA_HOME /usr/lib/jvm/java-11-openjdk
setenv ORACLE_HOME /u01/app/oracle/product/19c
