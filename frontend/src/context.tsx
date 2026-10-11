import React, { createContext, useContext } from 'react';
import { useStore } from './store';
import { StoreState } from './types';

type StoreContextType = {
  state: StoreState;
  updateState: (updater: (draft: StoreState) => StoreState) => void;
};

const StoreContext = createContext<StoreContextType | null>(null);

export const StoreProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const store = useStore();
  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
};

export const useGlobalStore = () => {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useGlobalStore must be used within StoreProvider');
  return ctx;
};
