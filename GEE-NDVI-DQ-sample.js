// Make a button widget.
var button = ui.Button('Click me!');

// Set a callback function to run when the
// button is clicked.
button.onClick(function() {
  print('Hello, world!');
});

// Display the button in the console.
print(button);
// Script to assess NDVI over time for any area smaller than a Sentinel 2 tile
// v0.1
// TODO: add mosaicing for larger area

// setting time frame
var startDate = '2020-07-01';
var endDate = '2021-07-07';

// Function to remove cloud and snow pixelsgeometry
function maskCloudAndShadows(image) {
  var qa = image.select('QA60');

  // Bits 10 and 11 are clouds and cirrus, respectively.
  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;

  // Both flags should be set to zero, indicating clear conditions.
  var mask = qa.bitwiseAnd(cloudBitMask).eq(0)
      .and(qa.bitwiseAnd(cirrusBitMask).eq(0));

  return image.updateMask(mask).divide(10000)
      //.select("B[0-9]*")
      .copyProperties(image, ["system:time_start"]);
}

// Adding a NDVI band and caluclating area
function addNDVI(image) {

  // calculate NDVI and area of ndvi >0.2
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi');
  var ndvi02 = ndvi.gt(0.2);
  var ndviImg = image.addBands(ndvi).updateMask(ndvi02);
  var ndvi02Area = ndvi02.multiply(ee.Image.pixelArea()).rename('ndvi02Area');

  // adding area of vegetaion as a band
  ndviImg = ndviImg.addBands(ndvi02Area);

  // calculate ndvi >0.2 area
  var ndviStats = ndvi02Area.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: geometry,
    scale: 10,
    maxPixels: 2931819000
  });

  image = image.set(ndviStats);

  // calculate area of AOI
  var area = image.select('B1').multiply(0).add(1).multiply(ee.Image.pixelArea()).rename('area');

  // calculate area
  var imgStats = area.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: geometry,
    scale: 10,
    maxPixels: 2931819000
  });
  image = image.set(imgStats);

  var a = image.getNumber('ndvi02Area').divide(image.getNumber('area')).multiply(100);
  var b = image.getNumber('ndvi02Area');
  //var pixelArea = image.multiply(ee.Image.pixelArea()).rename('a');

  var relCover = image.select('B1').multiply(0).add(a).rename('relNDVI');
  image = image.addBands(relCover);
  image = image.addBands(ndvi);//.updateMask(ndvi02);

  var thres = ndvi.gte(0.2).rename('thres');
  image = image.addBands(thres);
  image = image.addBands(b);
  return(image);
}

// Use Sentinel-2 data
var collection = ee.ImageCollection('COPERNICUS/S2')
    .filterDate(startDate, endDate)
    .filterBounds(geometry)
    .map(function(image){return image.clip(geometry)})
    //.map(maskCloudAndShadows) this is done further down separatly
    //.map(addNDVI)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',1));
    //not needed as we mask the clouds


var ndviCollection = collection.map(addNDVI); //.map(maskCloudAndShadows);
print(ndviCollection);

var triplets = ndviCollection.map(function(image) {
  return image.select('ndvi').reduceRegions({
    collection: geometry,
    reducer: ee.Reducer.first().setOutputs(['ndvi']),
    scale: 10,
  })
    // reduceRegion doesn't return any output if the image doesn't intersect
    // with the point or if the image is masked out due to cloud
    // If there was no ndvi value found, we set the ndvi to a NoData value -9999

    .map(function(feature) {
    var ndvi = ee.List([feature.get('ndvi'), -9999])
      .reduce(ee.Reducer.firstNonNull());
    return feature.set({'ndvi': ndvi, 'imageID': image.id()});
    });
  }).flatten();

var format = function(table, rowId, colId) {
  var rows = table.distinct(rowId);
  var joined = ee.Join.saveAll('matches').apply({
    primary: rows,
    secondary: table,
    condition: ee.Filter.equals({
      leftField: rowId,
      rightField: rowId
    })
  });

  return joined.map(function(row) {
      var values = ee.List(row.get('matches'))
        .map(function(feature) {
          feature = ee.Feature(feature);
          return [feature.get(colId), feature.get('ndvi')];
        });
      return row.select([rowId]).set(ee.Dictionary(values.flatten()));
    });
};
var sentinelResults = format(triplets, 'id', 'imageID');


// There are multiple image granules for the same date processed from the same orbit
// Granules overlap with each other and since they are processed independently
// the pixel values can differ slightly. So the same pixel can have different NDVI
// values for the same date from overlapping granules.
// So to simplify the output, we can merge observations for each day
// And take the max ndvi value from overlapping observations
var merge = function(table, rowId) {
  return table.map(function(feature) {
    var id = feature.get(rowId)
    var allKeys = feature.toDictionary().keys().remove(rowId)
    var substrKeys = ee.List(allKeys.map(function(val) {
        return ee.String(val).slice(0,8)}
        ))
    var uniqueKeys = substrKeys.distinct()
    var pairs = uniqueKeys.map(function(key) {
      var matches = feature.toDictionary().select(allKeys.filter(ee.Filter.stringContains('item', key))).values()
      var val = matches.reduce(ee.Reducer.max())
      return [key, val]
    })
    return feature.select([rowId]).set(ee.Dictionary(pairs.flatten()))
  })
};
var sentinelMerged = merge(sentinelResults, 'id');
print(sentinelMerged);

/// Define the chart and print it to the console.
var relCoverChart =
    ui.Chart.image
        .series({
          imageCollection: ndviCollection.select(['relNDVI']),
          region: geometry,
          reducer: ee.Reducer.mean(),
          scale: 10,
          xProperty: 'system:time_start'
        })

        .setOptions({
          title: 'Relative vegetation cover',
          hAxis: {title: 'Date', titleTextStyle: {italic: false, bold: true}},
          vAxis: {
            title: 'Vegetation cover (%)',
            titleTextStyle: {italic: false, bold: true}
          },
          lineWidth: 1,
          trendlines: {0: {
        color: 'CC0000'
      }},
          curveType: 'function'
        });
print(relCoverChart);

var ndviChart =
    ui.Chart.image
        .series({
          imageCollection: ndviCollection.select(['ndvi']),
          region: geometry,
          reducer: ee.Reducer.mean(),
          scale: 10,
          xProperty: 'system:time_start'
        })
        .setOptions({
          title: 'Mean NDVI value',
          hAxis: {title: 'Date', titleTextStyle: {italic: false, bold: true}},
          vAxis: {
            title: 'ndviChart',
            titleTextStyle: {italic: false, bold: true}
          },
          lineWidth: 1,
          trendlines: {0: {
        color: 'CC0000'
      }},
      curveType: 'function'
        });
print(ndviChart);


var DOYchart = ui.Chart.image
                .doySeriesByYear({
                  imageCollection: ndviCollection,
                  bandName: 'relNDVI',
                  region: geometry,
                  scale: 10,
                  sameDayReducer: ee.Reducer.mean(),
                  startDay: 1,
                  endDay: 365
                })
                .setOptions({
                  title: 'Average NDVI Value by Day of Year ',
                  hAxis: {
                    title: 'Day of year',
                    titleTextStyle: {italic: false, bold: true}
                  },
                  vAxis: {
                    title: 'Relative vegetation cover',
                    titleTextStyle: {italic: false, bold: true}
                  },
                  lineWidth: 1,
                  curveType: 'function'
                });
print(DOYchart);

/// Define the chart and print it to the console.
var absCoverChart =
    ui.Chart.image
        .series({
          imageCollection: ndviCollection.select(['constant']),
          region: geometry,
          reducer: ee.Reducer.mean(),
          scale: 10,
          xProperty: 'system:time_start'
        })
        .setOptions({
          title: 'Absolute vegetation cover',
          hAxis: {title: 'Date', titleTextStyle: {italic: false, bold: true}},
          vAxis: {
            title: 'Vegetation cover (m2)',
            titleTextStyle: {italic: false, bold: true}
          },
          lineWidth: 1,
          trendlines: {0: {
        color: 'CC0000'
      }},
          curveType: 'function'
        });
print(absCoverChart);

// difference between first and last
var firstImg = ndviCollection.limit(1, 'system:time_start', true).first();
var lastImg = ndviCollection.limit(1, 'system:time_start', false).first();


var diff = lastImg.subtract(firstImg).select('thres');
var maskneg = diff.eq(-1);
var maskpos = diff.eq(1);

var masknegImg = diff.updateMask(maskneg);
var maskposImg = diff.updateMask(maskpos);

// calculate area
var imgStatsPos = maskposImg.reduceRegion({
  reducer: ee.Reducer.sum(),
  geometry: geometry,
  scale: 10,
  maxPixels: 2931819000
});
print(imgStatsPos)
print(diff)
diff = diff.set(imgStatsPos)

var imgStatsNeg = masknegImg.reduceRegion({
  reducer: ee.Reducer.sum(),
  geometry: geometry,
  scale: 10,
  maxPixels: 2931819000
});

print(imgStatsNeg);
diff = diff.set(imgStatsNeg);

var ndviviz = {min: -1, max: 1, palette: ['red','green']};
var ndviviz1 = {min: 0, max: 1, palette: ['red','green']};
var visualization = { min: 0.0,
  max: 3000,
  bands: ['B4', 'B3', 'B2']
};

var geometryVis = {color: 'white'};
//Map.addLayer(lastImg,visualization,'RGB');
Map.addLayer(geometry, geometryVis, 'DQ',1, 0.75);
Map.addLayer(masknegImg.select('thres'),ndviviz,'Vegetation decrease');
Map.addLayer(maskposImg.select('thres'),ndviviz,'Vegetation increase');

var NDVImaskfirst = firstImg.select('thres').eq(1);
var NDVImasklast = lastImg.select('thres').eq(1);

var NDVImaskfirst = firstImg.updateMask(NDVImaskfirst);
var NDVImasklast = lastImg.updateMask(NDVImasklast);
Map.addLayer(NDVImaskfirst.select('thres'),ndviviz1,'First Imgae');
Map.addLayer(NDVImasklast.select('thres'),ndviviz1,'Last Imgae');

//Map.addLayer(firstImg.select('thres'),ndviviz,'First Image');
Map.centerObject(geometry, 14)
//Map.addLayer(geometry, {color: '000000'}, 'planar polygon');
var centroid = geometry.first().geometry().centroid();
//print()

//Map.addLayer(plotImg, visualization, 'RGB');
