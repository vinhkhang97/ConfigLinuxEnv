:  au BufNewFile,BufRead *.src      set  filetype=asm
:  au BufNewFile,BufRead *.equ      set  filetype=asm
:  au BufNewFile,BufRead *.def      set  filetype=asm
:  au BufNewFile,BufRead *.lis      set  filetype=asm
:  au BufNewFile,BufRead *.dis      set  filetype=asm
:  au BufNewFile,BufRead *.inc      set  filetype=asm 
:  au BufNewFile,BufRead *.txt      set  filetype=verilog 
:  au BufNewFile,BufRead *.sv       set  filetype=verilog 
:  au BufNewFile,BufRead *.l        set  filetype=text
:  au BufNewFile,BufRead *.sh       set  filetype=csh
:  au BufNewFile,BufRead *.csh      set  filetype=csh
:  au BufNewFile,BufRead *.scr      set  filetype=csh
:  au BufNewFile,BufRead *Makefile  set  filetype=make
:  au BufNewFile,BufRead *.CSHRC    set  filetype=csh
:  au BufNewFile,BufRead *.cmd      set  filetype=csh
:  au BufNewFile,BufRead *.vf       set  filetype=verilog
:  au BufNewFile,BufRead *.lib      set  filetype=verilog
:  au BufNewFile,BufRead *.def      set  filetype=verilog
:  au BufNewFile,BufRead *.nc       set  filetype=csh
:  au BufNewFile,BufRead *.vcs      set  filetype=csh 
":au BufNewFile,BufRead *.vh       set  filetype=verilog
:  set ignorecase smartcase
:  set incsearch
:  set nocompatible
:  set backspace=indent,eol,start
:  set autoindent
:  set history=10000
:  set nobackup
:  set clipboard=unnamed
:  syntax on
:  set showcmd
:  set nowrap
:  set paste
:  set showmatch
:  set linebreak
:  set ruler
:  set hlsearch
:  set cursorcolumn
:  set cursorline
:  set expandtab
:  set sw=2
:  set backspace=indent,eol,start
"=======================================
":  map <F1> :<ESC><Home>i#<ESC>j
":  map <F2> :<ESC><Home><Del><ESC>j
:  map <F3> :<ESC>:w!<ESC>
:  map <F4> :<ESC><C-W>:w<ESC>
:  map <F5> :<ESC>:set nu<ESC>
:  map <F6> :<ESC>:set nonu<ESC>
:  map <F7> :<ESC>:q<ESC>
:  map <F8> :<ESC>:q!<ESC>
:  map <F9> :<ESC>:set wrap<ESC>
:  map <F10> :<ESC>:set nowrap<ESC>
:  map <F11> :<ESC>:set mouse=a<ESC>
:  map <F12> :<ESC>:set mouse=i<ESC>
        
if (@% =~ "[\.]src$" || @% =~ "[\.]ms$" ||  @% =~ "[\.]asm$" )     "if file is *.src or *.ms or *.asm
   set ft=asm
   map <F1> :<ESC>0i;;<ESC>j
elseif (@% =~ "[\.]log$")
   map <F1> :<ESC>0i------------------------- <ESC>j
   map <F2> :<ESC>0xxxxxxxxxxxxxxxxxxxxxxxxxx<ESC>j
   map <F3> :<ESC>0i//####################### <ESC>j
   map <F4> :<ESC>0xxxxxxxxxxxxxxxxxxxxxxxxxx<ESC>j
elseif (@% =~ "[\.]S$" || @% =~ "[\.]h$" || @% =~ "[\.]s$")   "if file is *.S or *.h  (for G3M)
   map <F1> :<ESC>0i-- <ESC>j
   map <F2> :<ESC>0xx<ESC>j
"   map <F3> :<ESC>0i#<ESC>j
"   map <F4> :<ESC>0xx<ESC>j
elseif (@% =~ "[\.]v$" || @% =~ "[\.]V$" || @% =~ "[\.]sv$"|| @% =~ "[\.]vg" || @% =~ "[\.]vc" || @% =~ "[\.]php")
   map <F1> :<ESC>0i// <ESC>j
   map <F2> :<ESC>0xx<ESC>j
elseif (@% =~ "[\.]pl$" || @% =~ "[\.]csh$" || @% =~ "[\.]sh$" || @%=~ "[\.]tcl$" || @% =~ "[\.]lib$") "if file is .
   map <F1> :<ESC>0i#<ESC>j
elseif (@% =~ "\.vimrc") "if file is .pl+.csh+.sh+.tcl+.lib
   map <F1> :<ESC>0i"<ESC>j
elseif (@% =~ "_RTL_LIST$")
   map <F5> :<ESC><End>a -simvopt +vpd<ESC>j
   map <F6> :<ESC><End>xxxxxxxxxxxxxj
elseif (@% =~ "muverc$")
"                        map <F5> :<ESC><End><Home>i#<ESC>oBS="bs -m
"                        HOSTGR_MENTOR -os RHEL5 -source
"                        ${ENV_SIM}/sourceMe"<ESC>
"                           map <F6> :<ESC.io><End>ddk<Home>x
elseif (@% =~ ".io$")
   set noexpandtab      
endif
"___________________________
"
"       Highlighting
"___________________________
if ($TERM == "xterm")
   set t_Co=256                        "Enable 256-color mode
endif

if (&t_Co == 256)
   set cursorline cursorcolumn
"   highlight Search cterm=none  ctermbg=115
   highlight Search cterm=none  ctermbg=115
   highlight CursorLine cterm=none  ctermbg=8
   highlight CursorColumn cterm=none ctermbg=8
   highlight DiffText cterm=bold ctermbg=210 ctermfg=12 
endif
colorscheme monokai 

"if &term =~ "xterm\\|rxvt"
"  " use an orange cursor in insert mode
"  let &t_SI = "\<Esc>]12;orange\x7"
"  " use a red cursor otherwise
"  let &t_EI = "\<Esc>]12;red\x7"
"  silent !echo -ne "\033]12;red\007"
"  " reset cursor when vim exits
"  autocmd VimLeave * silent !echo -ne "\033]112\007"
"  " use \003]12;gray\007 for gnome-terminal
