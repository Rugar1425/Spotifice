#!/bin/bash

tmux new-session -d -s session

tmux set-option -g mouse on
tmux setw -g monitor-activity on
tmux set-option -g visual-activity on
tmux bind-key x kill-session
tmux set-option -g set-titles off

tmux split-window -h
tmux split-window -v
tmux send-keys -t session:0.0 "./media_provider.py --Ice.Config=provider.config" C-m
tmux send-keys -t session:0.1 "./media_render.py --Ice.Config=render.config" C-m
tmux send-keys -t session:0.2 "./media_control.py --Ice.Config=control.config" C-m
tmux attach-session -t session
