import { createContext, useContext, useMemo, useState } from 'react';
import useSWR from 'swr';
import { api } from '../api/client';

const AppContext = createContext();

const fetcher = async (key, ...args) => api[key](...args);

export function AppProvider({ children }) {
  const [companyId, setCompanyIdState] = useState(
    localStorage.getItem('companyId') || ''
  );
  const [period, setPeriodState] = useState(
    localStorage.getItem('period') || new Date().toISOString().slice(0, 10)
  );

  const setCompanyId = value => {
    setCompanyIdState(value);
    localStorage.setItem('companyId', value);
  };

  const setPeriod = value => {
    setPeriodState(value);
    localStorage.setItem('period', value);
  };

  const {
    data: forecasts,
    error: forecastsError,
    mutate: mutateForecasts,
    isLoading: forecastsLoading,
  } = useSWR(companyId ? ['forecasts', companyId] : null, fetcher, {
    dedupingInterval: 60000,
    revalidateOnFocus: false,
  });

  const {
    data: variances,
    error: variancesError,
    mutate: mutateVariances,
    isLoading: variancesLoading,
  } = useSWR(companyId && period ? ['variances', companyId, period] : null, fetcher, {
    dedupingInterval: 60000,
    revalidateOnFocus: false,
  });

  const {
    data: commentary,
    error: commentaryError,
    mutate: mutateCommentary,
    isLoading: commentaryLoading,
  } = useSWR(companyId && period ? ['commentary', companyId, period] : null, fetcher, {
    dedupingInterval: 60000,
    revalidateOnFocus: false,
  });

  const refreshAll = () => {
    mutateForecasts();
    mutateVariances();
    mutateCommentary();
  };

  const value = useMemo(
    () => ({
      companyId,
      setCompanyId,
      period,
      setPeriod,
      forecasts: forecasts || [],
      variances: variances || [],
      commentary,
      refreshAll,
      loading: {
        forecasts: forecastsLoading,
        variances: variancesLoading,
        commentary: commentaryLoading,
      },
      errors: {
        forecasts: forecastsError,
        variances: variancesError,
        commentary: commentaryError,
      },
    }),
    [
      companyId,
      commentary,
      commentaryError,
      commentaryLoading,
      forecasts,
      forecastsError,
      forecastsLoading,
      period,
      variances,
      variancesError,
      variancesLoading,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export const useApp = () => useContext(AppContext);
