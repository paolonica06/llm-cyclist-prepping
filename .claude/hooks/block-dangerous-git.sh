#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# NB: 'git push' normale è CONSENTITO (l'utente ha autorizzato il push autonomo).
# Restano bloccate solo le operazioni irreversibili: force-push e distruzioni locali.
# I pattern force-push catturano l'opzione ovunque compaia (anche dopo remote/branch).
DANGEROUS_PATTERNS=(
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "git push.*--force"
  "git push.* -f( |$)"
  "reset --hard"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' matches dangerous pattern '$pattern'. The user has prevented you from doing this." >&2
    exit 2
  fi
done

exit 0
