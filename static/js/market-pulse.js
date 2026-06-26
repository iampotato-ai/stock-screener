/* static/js/market-pulse.js */
class MarketPulse {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.svg = this.container.querySelector('.market-pulse-svg');
    this.scoreEl = this.container.querySelector('.market-pulse-score');
    this.deltaEl = this.container.querySelector('.market-pulse-delta');
    this.speed = options.speed || 0.02;
    this.particleCount = options.particleCount || 20;
    this.particles = [];
    this.score = options.initialScore || 50;
    this.animationFrameId = null;

    // Set initial ARIA attributes
    this.updateARIAAttributes();

    // Add keyboard event listeners for accessibility
    this.container.setAttribute('tabindex', '0');
    this.container.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        // Trigger click action
        this.container.click();
      }
    });

    window.marketPulse = this;

    this.init();
    this.animate();
  }

  updateARIAAttributes() {
    // Update ARIA values based on current score
    this.container.setAttribute('aria-valuenow', this.score);

    // Update aria-label with current state
    const label = this.container.querySelector('.market-pulse-label')?.textContent || 'Market Regime';
    const scoreText = this.scoreEl ? this.scoreEl.textContent : '--';
    const bandEl = document.getElementById('regime-band');
    const bandText = bandEl ? bandEl.textContent : '';

    this.container.setAttribute('aria-label', `${label}: ${scoreText}, ${bandText}`);
  }

  init() {
    if (!this.svg) return;

    // Create particles
    for (let i = 0; i < this.particleCount; i++) {
      this.particles.push({
        x: Math.random() * 100,
        y: Math.random() * 100,
        radius: Math.random() * 2 + 1,
        speedX: (Math.random() - 0.5) * this.speed * 10,
        speedY: (Math.random() - 0.5) * this.speed * 10,
        opacity: Math.random() * 0.6 + 0.2
      });
    }

    // Create SVG elements that we'll update rather than recreate
    this.particleElements = [];
    for (let i = 0; i < this.particleCount; i++) {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('fill', `var(--color-accent)`);
      this.svg.appendChild(circle);
      this.particleElements.push(circle);
    }

    // Create track element
    this.trackElement = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    this.trackElement.setAttribute('fill', 'none');
    this.trackElement.setAttribute('stroke', `var(--color-accent-track)`);
    this.trackElement.setAttribute('stroke-width', '8');
    this.svg.appendChild(this.trackElement);

    // Create arc element
    this.arcElement = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    this.arcElement.setAttribute('fill', 'none');
    this.arcElement.setAttribute('stroke', `var(--color-accent)`);
    this.arcElement.setAttribute('stroke-width', '6');
    this.arcElement.setAttribute('stroke-linecap', 'round');
    this.svg.appendChild(this.arcElement);

    // Initial render
    this.render();
  }

  updateScore(score, delta) {
    this.score = Math.max(0, Math.min(100, score));
    if (this.scoreEl) this.scoreEl.textContent = this.score;

    // Set dynamic accent color based on regime score
    let accentColor = '#F59E0B'; // default Neutral (amber)
    if (this.score >= 75) accentColor = '#10B981';      // Bull Run (green)
    else if (this.score >= 55) accentColor = '#14B8A6'; // Bullish (teal)
    else if (this.score >= 40) accentColor = '#F59E0B'; // Neutral (amber)
    else if (this.score >= 20) accentColor = '#F97316'; // Bearish (orange)
    else accentColor = '#EF4444';                      // Bear Market (red)

    if (this.container) {
      this.container.style.setProperty('--color-accent', accentColor);
    }

    if (this.deltaEl && delta !== undefined) {
      const absDelta = Math.abs(delta);
      this.deltaEl.textContent = delta >= 0 ? `▲ ${absDelta}` : `▼ ${absDelta}`;
      this.deltaEl.className = `market-pulse-delta ${delta >= 0 ? 'positive' : 'negative'}`;
    }

    // Adjust particle speed based on score (more energy = faster movement)
    const speedFactor = 0.5 + (this.score / 100) * 1.5;
    this.particles.forEach(p => {
      const currentSpeedX = Math.abs(p.speedX);
      const currentSpeedY = Math.abs(p.speedY);
      const speedX = currentSpeedX > 0 ? currentSpeedX : 0.1;
      const speedY = currentSpeedY > 0 ? currentSpeedY : 0.1;
      p.speedX = (p.speedX / speedX) * speedX * speedFactor * 0.5;
      p.speedY = (p.speedY / speedY) * speedY * speedFactor * 0.5;
    });

    this.render();

    // Update ARIA attributes when score changes
    this.updateARIAAttributes();

    // Dispatch custom event for external listeners
    if (this.container) {
      this.container.dispatchEvent(new CustomEvent('market-pulse-update', {
        detail: { score: this.score, delta: delta }
      }));
    }
  }

  render() {
    if (!this.svg) return;

    // Update particles
    this.particles.forEach((p, index) => {
      const circle = this.particleElements[index];
      if (circle) {
        circle.setAttribute('cx', p.x);
        circle.setAttribute('cy', p.y);
        circle.setAttribute('r', p.radius);
        circle.setAttribute('opacity', p.opacity);
      }
    });

    // Update track
    if (this.trackElement) {
      this.trackElement.setAttribute('cx', '60');
      this.trackElement.setAttribute('cy', '60');
      this.trackElement.setAttribute('r', '50');
    }

    // Update score arc (progress indicator)
    if (this.arcElement) {
      const endAngle = (this.score / 100) * 2 * Math.PI;
      const largeArc = this.score > 50 ? '1' : '0';
      const d = `
        M 60,10
        A 50,50 0 ${largeArc} 1
        ${60 + 50 * Math.sin(endAngle)},${60 - 50 * Math.cos(endAngle)}
      `;
      this.arcElement.setAttribute('d', d.trim());
    }
  }

  animate() {
    if (!this.svg) return;

    // Update particle positions
    this.particles.forEach(p => {
      p.x += p.speedX;
      p.y += p.speedY;

      // Wrap around boundaries using actual SVG dimensions
      const svgWidth = this.svg.width.baseVal.value || this.svg.viewBox.baseVal.width || 120;
      const svgHeight = this.svg.height.baseVal.value || this.svg.viewBox.baseVal.height || 120;

      if (p.x < 0) p.x = svgWidth;
      if (p.x > svgWidth) p.x = 0;
      if (p.y < 0) p.y = svgHeight;
      if (p.y > svgHeight) p.y = 0;
    });

    this.render();
    this.animationFrameId = requestAnimationFrame(() => this.animate());
  }

  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }
}

// Auto-initialize if element exists
document.addEventListener('DOMContentLoaded', () => {
  const pulseContainer = document.getElementById('market-pulse');
  if (pulseContainer) {
    const initialScore = pulseContainer.getAttribute('data-initial-score') || 65;
    new MarketPulse('market-pulse', {
      initialScore: parseInt(initialScore),
      speed: 0.015
    });
  }
});