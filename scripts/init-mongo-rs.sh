#!/usr/bin/env bash
# Run once after the first deploy of the mongo StatefulSet to form the replica set.
set -euo pipefail

NS="${NS:-social}"

kubectl -n "$NS" exec -it mongo-0 -- mongosh --eval '
  rs.initiate({
    _id: "rs0",
    members: [
      { _id: 0, host: "mongo-0.mongo:27017" },
      { _id: 1, host: "mongo-1.mongo:27017" },
      { _id: 2, host: "mongo-2.mongo:27017" }
    ]
  });
'
