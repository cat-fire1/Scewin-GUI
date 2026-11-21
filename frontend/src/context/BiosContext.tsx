import { createContext, useContext, type ReactNode } from 'react';
import type { BiosGateway } from '../types';

const BiosContext = createContext<BiosGateway | null>(null);

export function BiosProvider({ gateway, children }: { gateway: BiosGateway; children: ReactNode }) {
  return <BiosContext.Provider value={gateway}>{children}</BiosContext.Provider>;
}

export function useBiosGateway(): BiosGateway {
  const context = useContext(BiosContext);
  if (!context) throw new Error('useBiosGateway must be used within BiosProvider');
  return context;
}
