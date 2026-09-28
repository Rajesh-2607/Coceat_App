import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Schemas } from "../api/client";
import { useLocations } from "../api/hooks";
import { Loading } from "../lib/ui";

type Ctx = {
  /** null = all of the member's locations */
  locationId: string | null;
  setLocationId: (id: string | null) => void;
  locations: Schemas["LocationOut"][];
};

const LocationContext = createContext<Ctx>({ locationId: null, setLocationId: () => {}, locations: [] });

const storageKey = (businessId: string) => `cocreat.location.${businessId}`;

function readStored(businessId: string): string | null {
  try {
    return localStorage.getItem(storageKey(businessId));
  } catch {
    return null;
  }
}

/** The location switcher's state. Persisted per business so a shop counter stays on its shop. */
export function LocationProvider({ businessId, children }: { businessId: string; children: ReactNode }) {
  const query = useLocations();
  const [stored, setStored] = useState<string | null>(() => readStored(businessId));
  const locations = useMemo(() => (query.data ?? []).filter((l) => l.is_active), [query.data]);
  // a stored id that no longer exists (deactivated, or access removed) falls back to "all"
  const locationId = stored !== null && locations.some((l) => l.id === stored) ? stored : null;

  const value = useMemo<Ctx>(
    () => ({
      locationId,
      locations,
      setLocationId: (id) => {
        setStored(id);
        try {
          if (id === null) localStorage.removeItem(storageKey(businessId));
          else localStorage.setItem(storageKey(businessId), id);
        } catch {
          // private mode: the choice just won't persist
        }
      },
    }),
    [locationId, locations, businessId],
  );
  // screens pick their default location from this list, so wait for it (an error, e.g. module off, just means none)
  if (query.isPending) return <Loading />;
  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useCurrentLocation() {
  return useContext(LocationContext);
}
