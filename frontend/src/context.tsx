import React, { createContext, useContext, useState } from 'react';
import { useStore } from './store';
import { StoreState } from './types';

export type ClusterSiteId = 'QUITO' | 'GUAYAQUIL' | 'CUENCA_CLOUD';

type StoreContextType = {
  state: StoreState;
  updateState: (updater: (draft: StoreState) => StoreState) => void;
  activeSite: ClusterSiteId;
  setActiveSite: (site: ClusterSiteId) => void;
};

const StoreContext = createContext<StoreContextType | null>(null);

export const StoreProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const store = useStore();
  const [activeSite, setActiveSite] = useState<ClusterSiteId>('QUITO');
  return (
    <StoreContext.Provider value={{ ...store, activeSite, setActiveSite }}>
      {children}
    </StoreContext.Provider>
  );
};

export const useGlobalStore = () => {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useGlobalStore must be used within StoreProvider');
  return ctx;
};
