#!/bin/sh
set -e

# Ensure the working directory is correct
cd /app



# Replace NEXT_PUBLIC_* placeholder tokens baked into the client bundle at build
# time with the real runtime values. Parsing notes:
#   - key=${line%%=*} / value=${line#*=} keeps EVERYTHING after the first '='
#     (cut -f2 truncated any value containing '=', e.g. base64 / query strings).
#   - sed metacharacters in the value (& \ and the | delimiter) are escaped so a
#     URL or secret containing them cannot corrupt the replacement.
printenv | grep '^NEXT_PUBLIC_' | while IFS= read -r line ; do
  key=${line%%=*}
  value=${line#*=}

  escaped_value=$(printf '%s' "$value" | sed -e 's/[&|\\]/\\&/g')
  find .next/ -type f -exec sed -i "s|$key|$escaped_value|g" {} \;
done
echo "Done replacing env variables NEXT_PUBLIC_ with real values"


# Execute the container's main process (CMD in Dockerfile)
exec "$@"