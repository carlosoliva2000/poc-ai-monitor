'use client'

import { useCallback, useEffect, useState } from 'react'

/**
 * Estado que se recuerda en `localStorage`. Todo acceso va en `try/catch` (puede fallar o estar
 * bloqueado): sin almacenamiento se usa el valor inicial. `revive` completa o corrige lo leído.
 */
export function useStoredState<T>(key: string, initial: T, revive: (raw: unknown) => T = (raw) => raw as T) {
  const [value, setValue] = useState<T>(initial)
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key)
      if (raw) setValue(revive(JSON.parse(raw)))
    } catch {
      /* sin almacenamiento: se queda el valor inicial */
    }
    // `revive` es estable por llamada; solo se lee al montar
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  const update = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const value = typeof next === 'function' ? (next as (p: T) => T)(prev) : next
        try {
          window.localStorage.setItem(key, JSON.stringify(value))
        } catch {
          /* ídem */
        }
        return value
      })
    },
    [key],
  )
  return [value, update] as const
}
