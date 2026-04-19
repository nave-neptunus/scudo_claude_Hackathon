import React, { useRef, useEffect } from "react";
import * as d3 from "d3";
import * as topojson from "topojson-client";

export function D3WorldMap({ events, boms }) {
  const svgRef = useRef();
  
  useEffect(() => {
    fetch('https://unpkg.com/world-atlas@2.0.2/countries-110m.json')
      .then(r => r.json())
      .then(world => {
         const countries = topojson.feature(world, world.objects.countries).features;
         const svg = d3.select(svgRef.current);
         svg.selectAll("*").remove();

         const node = svg.node();
         if (!node) return;
         const width = node.getBoundingClientRect().width;
         const height = node.getBoundingClientRect().height;

         const projection = d3.geoNaturalEarth1()
            .scale(width / 5.5)
            .translate([width / 2, height / 2 + 50]);
         const path = d3.geoPath().projection(projection);

         const g = svg.append("g");

         g.selectAll("path.country")
            .data(countries)
            .enter().append("path")
            .attr("class", "country")
            .attr("d", path)
            .attr("stroke", "rgba(0,0,0,0.06)")
            .attr("stroke-width", 1)
            .attr("fill", d => {
               // Extract all countries from BOMs
               const allCountries = new Set();
               boms.forEach(b => (b.rows || []).forEach(r => {
                  if (r.supplier_country) allCountries.add(r.supplier_country.toLowerCase());
               }));
               
               const cname = (d.properties?.name || "").toLowerCase();
               if (allCountries.has(cname)) {
                   // Check if this country is in active events
                   const inEvent = events.some(ev => JSON.stringify(ev).toLowerCase().includes(cname));
                   return inEvent ? "rgba(209,67,67,0.15)" : "rgba(76,111,174,0.15)";
               }
               return "rgba(255,255,255,0.7)";
            });

         const usCoords = projection([-95.7, 37.0]);
         if (!usCoords) return;

         const defs = svg.append("defs");
         const filter = defs.append("filter").attr("id", "glow");
         filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "coloredBlur");
         const feMerge = filter.append("feMerge");
         feMerge.append("feMergeNode").attr("in", "coloredBlur");
         feMerge.append("feMergeNode").attr("in", "SourceGraphic");

         const drawArc = (source, target, color) => {
           if (!source || !target) return;
           const arc = d3.line().curve(d3.curveBasis)([
             source,
             [ (source[0]+target[0])/2, Math.min(source[1], target[1]) - 150 ],
             target
           ]);
           
           const line = svg.append("path")
              .attr("d", arc)
              .attr("fill", "none")
              .attr("stroke", color)
              .attr("stroke-width", 2)
              .attr("stroke-dasharray", "6,4")
              .attr("opacity", 0.8)
              .style("filter", "url(#glow)");

           const totalLength = line.node().getTotalLength();
           line
             .attr("stroke-dasharray", totalLength + " " + totalLength)
             .attr("stroke-dashoffset", totalLength)
             .transition()
             .duration(2000)
             .attr("stroke-dashoffset", 0)
             .on("end", function() {
                d3.select(this)
                  .attr("stroke-dasharray", "6,4")
                  .style("animation", "dash 20s linear infinite");
             });
         };

         const drawPulse = (coords, color) => {
           if (!coords) return;
           svg.append("circle")
              .attr("cx", coords[0]).attr("cy", coords[1])
              .attr("r", 4).attr("fill", color)
              .append("animate")
              .attr("attributeName", "r")
              .attr("values", "4;12;4")
              .attr("dur", "2s")
              .attr("repeatCount", "indefinite");
           svg.append("circle")
              .attr("cx", coords[0]).attr("cy", coords[1])
              .attr("r", 4).attr("fill", color)
              .append("animate")
              .attr("attributeName", "opacity")
              .attr("values", "1;0;1")
              .attr("dur", "2s")
              .attr("repeatCount", "indefinite");
         };

         drawPulse(usCoords, "var(--fg-1)"); // US destination hub

         // Draw actual BOM arcs
         const drawn = new Set();
         boms.forEach(b => {
             (b.rows || []).forEach(r => {
                 const cname = (r.supplier_country || "").toLowerCase();
                 if (drawn.has(cname)) return;
                 drawn.add(cname);
                 
                 const feature = countries.find(c => (c.properties?.name || "").toLowerCase() === cname);
                 if (feature) {
                     const coords = path.centroid(feature);
                     const inEvent = events.some(ev => JSON.stringify(ev).toLowerCase().includes(cname));
                     const color = inEvent ? "var(--sev-critical)" : "var(--domain-reshore)";
                     drawArc(coords, usCoords, color);
                     drawPulse(coords, color);
                 }
             });
         });
      });
  }, [events, boms]);

  return (
    <>
      <style>{`@keyframes dash { to { stroke-dashoffset: -1000; } }`}</style>
      <svg ref={svgRef} style={{width:'100%', height:'100%', pointerEvents:'none'}}/>
    </>
  );
}
