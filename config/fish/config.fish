# Ano Shell — Configuration Fish (Starship, eza, zoxide, onde-cli, palette dynamique)

# Ajouter ~/.local/bin au PATH
fish_add_path -g "$HOME/.local/bin"

if status is-interactive
    set -gx TERMINAL kitty

    # Prompt Starship + prompt transitoire compact
    if command -v starship >/dev/null 2>&1
        starship init fish | source
        function starship_transient_prompt_func
            starship module character
        end
        enable_transience
    end

    # Direnv + Zoxide
    command -v direnv >/dev/null 2>&1; and direnv hook fish | source
    command -v zoxide >/dev/null 2>&1; and zoxide init fish --cmd cd | source

    # eza en remplacement de ls
    if command -v eza >/dev/null 2>&1
        alias ls='eza --icons --group-directories-first -1'
    end

    # Abréviations Git & fichiers
    abbr lg 'lazygit'
    abbr gd 'git diff'
    abbr ga 'git add .'
    abbr gc 'git commit -am'
    abbr gl 'git log'
    abbr gs 'git status'
    abbr gst 'git stash'
    abbr gsp 'git stash pop'
    abbr gp 'git push'
    abbr gpl 'git pull'
    abbr gsw 'git switch'
    abbr gsm 'git switch main'
    abbr gb 'git branch'
    abbr gbd 'git branch -d'
    abbr gco 'git checkout'
    abbr gsh 'git show'

    abbr l 'ls'
    abbr ll 'ls -l'
    abbr la 'ls -a'
    abbr lla 'ls -la'
    abbr ff 'fastfetch'
    abbr music 'onde-cli'

    # Couleurs dynamiques du terminal générées par Ano Shell
    test -f "$HOME/.local/state/ano-shell/sequences.txt"; and cat "$HOME/.local/state/ano-shell/sequences.txt"

    # Marqueur OSC 133 pour le saut entre prompts dans Kitty
    function mark_prompt_start --on-event fish_prompt
        echo -en "\e]133;A\e\\"
    end

    # Personnalisations locales utilisateur
    set -q XDG_CONFIG_HOME; and set -l anoConf "$XDG_CONFIG_HOME/ano-shell"; or set -l anoConf "$HOME/.config/ano-shell"
    test -f "$anoConf/user-config.fish"; and source "$anoConf/user-config.fish"
end
