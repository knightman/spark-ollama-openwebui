#!/bin/bash

# Check Ollama container
ollama_running=$(docker ps -q -f name=ollama)
if [ -z "$ollama_running" ]; then
  echo "FAIL: Ollama container not running"
  ollama_pass=false
else
  ollama_pass=true
  if ! curl -s localhost:11434/api/tags > /dev/null; then
    echo "FAIL: Ollama API unreachable"
    ollama_pass=false
  else
    echo "PASS: Ollama container healthy"
  fi
fi

# Check Open WebUI container
owui_running=$(docker ps -q -f name=open-webui)
if [ -z "$owui_running" ]; then
  echo "FAIL: Open WebUI container not running"
  owui_pass=false
else
  owui_pass=true
  if ! curl -s localhost:3000 > /dev/null; then
    echo "FAIL: Open WebUI unreachable"
    owui_pass=false
  else
    echo "PASS: Open WebUI container healthy"
  fi
fi

if $ollama_pass && $owui_pass; then
  exit 0
else
  exit 1
fi
