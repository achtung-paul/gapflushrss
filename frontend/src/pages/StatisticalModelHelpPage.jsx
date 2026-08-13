import { Link } from 'react-router-dom'

// Reference page for the statistical model feature (per-client sigma
// 1-5 visibility/info-only settings, see models/statistical_model_
// setting.py and StatisticalModelPage.jsx). Linked from that settings
// page and from next to the bell curve chart on every analysis page
// (ToleranceChainSection.jsx, AnalysisReportPage.jsx) -- same routed-
// page pattern as AngledInterfaceHelpPage.jsx, since this app has no
// modal/tooltip infrastructure to hang the explanation off instead.
function StatisticalModelHelpPage() {
  return (
    <div className="help-page">
      <p>
        <Link to="/projects">&larr; Projects</Link>
      </p>
      <h2>Statistical model</h2>
      <p>
        In a standard normal distribution (bell curve), data spreads away from the mean (μ) in
        predictable intervals measured by sigma (σ). When evaluating a statistical fit or
        manufacturing tolerance, these ranges dictate the probability of an outcome falling
        within your limits.
      </p>
      <ul>
        <li>
          <strong>One Sigma (σ):</strong> Encompasses 68.27% of all data points. This represents
          the most common, expected variation in a standard process or fit.
        </li>
        <li>
          <strong>Two Sigma (σ):</strong> Encompasses 95.45% of all data points. It is frequently
          used to establish acceptable engineering tolerances and control chart limits.
        </li>
        <li>
          <strong>Three Sigma (σ):</strong> Encompasses 99.73% of all data points. This is the
          traditional standard for quality control, where any point falling outside this range is
          considered an anomaly or a &quot;defect.&quot;
        </li>
        <li>
          <strong>Four Sigma (σ):</strong> Encompasses 99.9937% of all data points. This means
          only about 63 points out of 1 million (or 1 in 15,787) will naturally fall outside this
          range. In manufacturing, a 4-sigma process is considered highly stable and efficient for
          non-critical consumer goods.
        </li>
        <li>
          <strong>Five Sigma (σ):</strong> Encompasses 99.999943% of all data points. At this
          level, only 0.57 points out of 1 million (or 1 in 1.74 million) will fall outside the
          limits. This extreme threshold is widely used in high-stakes fields like medical device
          manufacturing, aviation logistics, and advanced scientific research where failure
          carries a massive cost.
        </li>
      </ul>
    </div>
  )
}

export default StatisticalModelHelpPage
