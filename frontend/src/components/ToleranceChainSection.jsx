import { useCallback, useEffect, useState } from 'react'
import {
  createChainComponent,
  deleteChainComponent,
  getSimulation,
  listChainComponents,
  listProcessTypes,
  listToleranceClasses,
} from '../api/client.js'
import RssDistributionChart from './RssDistributionChart.jsx'

const RAG_LABELS = { green: 'Green', amber: 'Amber', red: 'Red' }

// Lets the user build the RSS tolerance chain for one Gap/Flush entry
// (brief step 4: component tolerances + assembly-process variation),
// then shows the computed 3/4/5 sigma simulation (brief steps 5-6)
// against the entry's own nominal/tolerance band.
function ToleranceChainSection({ entryId, nominal, upperLimit, lowerLimit }) {
  const [components, setComponents] = useState([])
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  const [contributorType, setContributorType] = useState('COMPONENT')
  const [description, setDescription] = useState('')
  const [toleranceValue, setToleranceValue] = useState('')

  const [processTypes, setProcessTypes] = useState([])
  const [selectedProcessTypeId, setSelectedProcessTypeId] = useState('')
  const [toleranceClasses, setToleranceClasses] = useState([])
  const [selectedToleranceClassId, setSelectedToleranceClassId] = useState('')

  const refresh = useCallback(() => {
    listChainComponents(entryId).then(setComponents).catch((err) => setError(err.message))
    getSimulation(entryId).then(setSimulation).catch((err) => setError(err.message))
  }, [entryId])

  useEffect(refresh, [refresh])

  useEffect(() => {
    listProcessTypes().then(setProcessTypes).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedProcessTypeId) {
      setToleranceClasses([])
      return
    }
    listToleranceClasses(selectedProcessTypeId)
      .then(setToleranceClasses)
      .catch((err) => setError(err.message))
  }, [selectedProcessTypeId])

  function handleSelectToleranceClass(classId) {
    setSelectedToleranceClassId(classId)
    const chosen = toleranceClasses.find((tc) => String(tc.tolerance_class_id) === classId)
    if (chosen) {
      setToleranceValue(String(chosen.value))
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      await createChainComponent(entryId, {
        contributor_type: contributorType,
        description,
        tolerance_value: Number(toleranceValue),
        tolerance_class_id: selectedToleranceClassId ? Number(selectedToleranceClassId) : null,
      })
      setDescription('')
      setToleranceValue('')
      setSelectedProcessTypeId('')
      setSelectedToleranceClassId('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = useCallback(
    async (chainComponentId) => {
      setError(null)
      try {
        await deleteChainComponent(chainComponentId)
        setPendingDeleteId(null)
        refresh()
      } catch (err) {
        setError(err.message)
      }
    },
    [refresh],
  )

  return (
    <div className="tolerance-chain">
      <h4>Tolerance chain</h4>
      {error && <p className="form-error">{error}</p>}

      {components.length === 0 && (
        <p>No chain components yet -- add component tolerances and assembly-process variations below.</p>
      )}

      <ul>
        {components.map((component) => (
          <li key={component.chain_component_id}>
            [{component.contributor_type}] {component.description}: ±{component.tolerance_value}{' '}
            {pendingDeleteId === component.chain_component_id ? (
              <>
                <span>Delete this contributor?</span>{' '}
                <button type="button" onClick={() => handleDelete(component.chain_component_id)}>
                  Yes
                </button>{' '}
                <button type="button" onClick={() => setPendingDeleteId(null)}>
                  No
                </button>
              </>
            ) : (
              <button type="button" onClick={() => setPendingDeleteId(component.chain_component_id)}>
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={handleSubmit} className="inline-form">
        <select value={contributorType} onChange={(e) => setContributorType(e.target.value)}>
          <option value="COMPONENT">Component tolerance</option>
          <option value="PROCESS">Assembly process variation</option>
        </select>
        <input
          type="text"
          placeholder="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />
        <select
          value={selectedProcessTypeId}
          onChange={(e) => {
            setSelectedProcessTypeId(e.target.value)
            setSelectedToleranceClassId('')
          }}
        >
          <option value="">(manual value)</option>
          {processTypes.map((processType) => (
            <option key={processType.process_type_id} value={processType.process_type_id}>
              {processType.name}
            </option>
          ))}
        </select>
        {selectedProcessTypeId && (
          <select
            value={selectedToleranceClassId}
            onChange={(e) => handleSelectToleranceClass(e.target.value)}
          >
            <option value="">Select class...</option>
            {toleranceClasses.map((toleranceClass) => (
              <option key={toleranceClass.tolerance_class_id} value={toleranceClass.tolerance_class_id}>
                {toleranceClass.class_name} (±{toleranceClass.value})
              </option>
            ))}
          </select>
        )}
        <input
          type="number"
          step="any"
          min="0"
          placeholder="Tolerance (±)"
          value={toleranceValue}
          onChange={(e) => setToleranceValue(e.target.value)}
          required
        />
        <button type="submit">Add contributor</button>
      </form>

      {simulation && (
        <>
          <table className="rss-results">
            <thead>
              <tr>
                <th>Sigma level</th>
                <th>Spread (±)</th>
                <th>Predicted range</th>
                <th>RAG</th>
              </tr>
            </thead>
            <tbody>
              {simulation.results.map((result) => (
                <tr key={result.sigma_level}>
                  <td>{result.sigma_level}σ</td>
                  <td>{result.spread.toFixed(3)}</td>
                  <td>
                    {result.lower_bound.toFixed(3)} to {result.upper_bound.toFixed(3)}
                  </td>
                  <td className={`rag-badge rag-${result.rag}`}>{RAG_LABELS[result.rag]}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <RssDistributionChart
            nominal={nominal}
            upperLimit={upperLimit}
            lowerLimit={lowerLimit}
            sigma1={simulation.sigma_1}
            results={simulation.results}
          />
        </>
      )}
    </div>
  )
}

export default ToleranceChainSection
