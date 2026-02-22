import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { initSentry } from './telemetry/sentry'
import { captureAndPersistAttribution, updateStoredAttribution } from './lib/attribution'
import { getAnonymousId } from './lib/anonymousId'
import { trackAcquisitionEvent } from './lib/analytics'
import { getTrialDisclosureVariant, isTrialDisclosureExperimentEnabled } from './lib/experiments'

initSentry()
const attribution = captureAndPersistAttribution()
const anonymousId = getAnonymousId()

if (isTrialDisclosureExperimentEnabled()) {
  const variant = getTrialDisclosureVariant(anonymousId)
  updateStoredAttribution({
    exp_trial_disclosure: variant,
    experiment_variant: variant,
    anonymous_id: anonymousId ?? undefined,
  })

  const exposureKey = `ace_exposure_logged_${variant}`
  if (typeof window !== 'undefined' && !window.sessionStorage.getItem(exposureKey)) {
    trackAcquisitionEvent(
      'experiment_exposure',
      {
        experiment: 'trial_disclosure_timing',
        variant,
      },
      {
        anonymous_id: anonymousId ?? undefined,
        source: attribution.source ?? attribution.src,
        experiment_variant: variant,
      },
    )
    window.sessionStorage.setItem(exposureKey, '1')
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
