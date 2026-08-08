import { Link } from 'react-router-dom'
import { AngleResolutionDiagram, StackingComparisonDiagram } from '../components/AngledInterfaceDiagrams.jsx'

// Reference page for the angled-interface DVA feature (direction ==
// Other on a Gap/Flush entry, see components/AngledInterfaceSection.jsx).
// Reached via a plain link from that panel -- this app has no
// modal/tooltip infrastructure to hang the explanation off, so a routed
// page follows the existing page-per-route convention instead.
function AngledInterfaceHelpPage() {
  return (
    <div className="help-page">
      <p>
        <Link to="/projects">&larr; Projects</Link>
      </p>
      <h2>Angled interface analysis</h2>
      <p>
        Most Gap/Flush measurements run along one vehicle axis -- X, Y, or Z -- and a straight ±
        tolerance chain is enough to stack them up. When two components meet at an angle instead,
        a manufacturing variation in X <em>and</em> one in Y both partly affect the gap, and the
        two have to be resolved with trigonometry before they can be combined. Setting an entry's
        direction to <strong>Other</strong> switches it into this angled calculator.
      </p>

      <h3>What to enter</h3>
      <p>
        The <strong>interface angle θ</strong> is the angle between the mating faces, in degrees
        (0&ndash;90). For each contributing component, enter its <strong>X tolerance</strong> and{' '}
        <strong>Y tolerance</strong> as positive ± magnitudes -- the manufacturing variation that
        component can have along vehicle X and along vehicle Y, independent of the angle.
      </p>

      <h3>How a tolerance gets resolved onto the interface</h3>
      <p>
        Each tolerance is scaled by how much of it actually lands along the angled interface:
      </p>
      <p>
        <code>Vx = Tx · cos θ</code> and <code>Vy = Ty · sin θ</code>
      </p>
      <AngleResolutionDiagram />
      <p className="angled-diagram-caption">
        At 45° both factors are 0.707 -- that's why a worked example at 45° can look like there's
        one shared constant. At 30° they're 0.866 and 0.500 instead: cos θ and sin θ are always
        computed separately, for whatever angle is actually entered.
      </p>

      <h3>Choosing Worst case or Statistical (RSS)</h3>
      <p>
        Once every row is resolved into its Vx and Vy, the entry's Total Angled Variation combines
        all of them one of two ways:
      </p>
      <ul>
        <li>
          <strong>Worst case</strong> adds every resolved value together -- the total if every
          contributor happened to hit its extreme, in the same direction, at the same time. This
          is the number you can guarantee will never be exceeded.
        </li>
        <li>
          <strong>Statistical (RSS)</strong> combines them in quadrature (square each one, add,
          take the square root) -- the total you'll actually see in practice, since real
          manufacturing variation is independent from part to part rather than all lining up at
          once. RSS is always the smaller of the two.
        </li>
      </ul>
      <StackingComparisonDiagram />
      <p className="angled-diagram-caption">
        Same four inputs, combined two ways. Worst case is what you can guarantee; RSS is what
        you'll typically measure.
      </p>

      <h3>How the result is judged</h3>
      <p>
        The Total Angled Variation is compared against the entry's own nominal value and upper/
        lower limits, using the same rule as every other result in this app: green if the
        predicted range stays fully inside the tolerance band, amber if it breaches a limit by up
        to 5% of that limit, red beyond that.
      </p>

      <h3>Worked example</h3>
      <p>
        An entry with nominal 5.000 mm, upper limit 1.500 mm, lower limit 1.500 mm (band 3.500 to
        6.500 mm), interface angle 45°, and two components:
      </p>
      <table>
        <thead>
          <tr>
            <th>Component</th>
            <th>X tolerance</th>
            <th>Y tolerance</th>
            <th>Vx</th>
            <th>Vy</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Bracket</td>
            <td>±1.0 mm</td>
            <td>±1.0 mm</td>
            <td>0.707 mm</td>
            <td>0.707 mm</td>
          </tr>
          <tr>
            <td>Fastener</td>
            <td>±0.5 mm</td>
            <td>±0.5 mm</td>
            <td>0.354 mm</td>
            <td>0.354 mm</td>
          </tr>
        </tbody>
      </table>
      <p>
        <strong>Worst case:</strong> 0.707 + 0.707 + 0.354 + 0.354 = <strong>±2.121 mm</strong>{' '}
        &rarr; predicted range 2.879 to 7.121 mm, which breaches the 6.500 mm upper limit by 0.621
        mm (far more than 5% of 1.500 mm) &rarr; <strong>Red</strong>.
      </p>
      <p>
        <strong>Statistical (RSS):</strong> √(0.707² + 0.707² + 0.354² + 0.354²) ={' '}
        <strong>±1.118 mm</strong> &rarr; predicted range 3.882 to 6.118 mm, fully inside the band
        &rarr; <strong>Green</strong>.
      </p>
      <p>
        Try these same numbers in an entry set to <strong>Other</strong> at 45° -- toggling between
        Worst case and RSS should reproduce this exactly, changing only the total and its colour,
        never the table.
      </p>
    </div>
  )
}

export default AngledInterfaceHelpPage
