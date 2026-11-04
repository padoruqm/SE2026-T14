export interface DistanceUnit {
  /** Text to show after a distance. */
  label: string
  /** True when coordinates are angles, so a straight-line distance is meaningless. */
  geographic: boolean
}

const EPSG = /^EPSG:(\d+)$/i

/**
 * Work out how to label distances for a CRS such as `EPSG:32648`. Only codes that
 * are clearly metric or clearly angular are recognised; everything else is
 * reported as plain "units" rather than guessed.
 */
export function distanceUnit(crs: string | null): DistanceUnit {
  const code = Number(EPSG.exec(crs?.trim() ?? '')?.[1])
  if (!Number.isInteger(code)) return { label: 'units', geographic: false }

  // EPSG 4000-4999 are geographic CRSs, except 4978 which is geocentric (metres).
  if (code >= 4000 && code <= 4999 && code !== 4978) return { label: '°', geographic: true }
  if (code === 4978 || code === 3857) return { label: 'm', geographic: false }
  // WGS 84 / UTM zones 1-60 north and south.
  if ((code >= 32601 && code <= 32660) || (code >= 32701 && code <= 32760)) {
    return { label: 'm', geographic: false }
  }
  return { label: 'units', geographic: false }
}
