import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { SpawnDefaults, api } from "./api";

export const FALLBACK_SPAWN_DEFAULTS: SpawnDefaults = {
  model: "llama3.1:8b",
  target_puller: "puller-01",
  temperature: 0.7,
  num_ctx: 8192,
};

export function useSpawnDefaults(): {
  spawnDefaults: SpawnDefaults;
  loading: boolean;
  setSpawnDefaults: Dispatch<SetStateAction<SpawnDefaults>>;
} {
  const [spawnDefaults, setSpawnDefaults] = useState<SpawnDefaults>(FALLBACK_SPAWN_DEFAULTS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.spawnDefaults()
      .then((defaults) => {
        if (active) setSpawnDefaults(defaults);
      })
      .catch(() => {
        if (active) setSpawnDefaults(FALLBACK_SPAWN_DEFAULTS);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return { spawnDefaults, loading, setSpawnDefaults };
}
