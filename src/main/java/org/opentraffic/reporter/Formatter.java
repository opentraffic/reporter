package org.opentraffic.reporter;

import java.io.IOException;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

import org.joda.time.DateTime;
import org.joda.time.format.DateTimeFormat;
import org.joda.time.format.DateTimeFormatter;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class Formatter {
  private enum Type { SV, JSON };
  //shared stuff
  private Type type;
  private DateTimeFormatter timeFormatter;
  private DecimalFormat floatFormatter;
  //sv stuff
  private String separator;
  private int uuid_index, lat_index, lon_index, time_index, accuracy_index;
  //json stuff
  private String uuid_key, lat_key, lon_key, time_key, accuracy_key;
  
  //hide this you have to use a supported type
  private Formatter() {
    floatFormatter = new DecimalFormat("###.######", new DecimalFormatSymbols(Locale.US));
  }
  
  public static Formatter SVFormatter(String separator, int uuid_index, int lat_index, int lon_index, int time_index, int accuracy_index) {
    return SVFormatter(separator, uuid_index, lat_index, lon_index, time_index, accuracy_index, null);
  }
  public static Formatter SVFormatter(String separator, int uuid_index, int lat_index, int lon_index, int time_index, int accuracy_index, String time_format) {
    Formatter f = new Formatter();
    f.type = Type.SV;
    f.separator = separator;
    f.uuid_index = uuid_index;
    f.lat_index = lat_index;
    f.lon_index = lon_index;
    f.time_index = time_index;
    f.accuracy_index = accuracy_index;
    f.timeFormatter = time_format != null ? DateTimeFormat.forPattern(time_format).withLocale(Locale.US).withZoneUTC() : null;
    return f;
  }
  
  public static Formatter JSONFormatter(String uuid_key, String lat_key, String lon_key, String time_key, String accuracy_key) {
    return JSONFormatter(uuid_key, lat_key, lon_key, time_key, accuracy_key, null);
  }
  public static Formatter JSONFormatter(String uuid_key, String lat_key, String lon_key, String time_key, String accuracy_key, String time_format) {
    Formatter f = new Formatter();
    f.type = Type.JSON;
    f.uuid_key = uuid_key;
    f.lat_key = lat_key;
    f.lon_key = lon_key;
    f.time_key = time_key;
    f.accuracy_key = accuracy_key;
    f.timeFormatter = time_format != null ? DateTimeFormat.forPattern(time_format).withLocale(Locale.US).withZoneUTC() : null;
    return f;
  }
  
  //TODO: protobuf/other formatter

  public Pair<String, Point> format(String message) throws ParseException, IOException {
    switch(type) {
    case SV:
      return formatSV(message);
    case JSON:
      return formatJSON(message);
    default:
      throw new RuntimeException("Unsupported format");  
    }
  }
  
  private Pair<String, Point> formatSV(String message) throws ParseException {
    //parse it
    String[] parts = message.split(separator);
    //pull out each value
    float lat = floatFormatter.parse(parts[lat_index]).floatValue();
    float lon = floatFormatter.parse(parts[lon_index]).floatValue();
    long time = timeFormatter != null ? 
      DateTime.parse(parts[time_index], timeFormatter).getMillis() / 1000l : 
      Long.parseLong(parts[time_index]);
    int accuracy = (int)Math.ceil(floatFormatter.parse(parts[accuracy_index]).floatValue());
    //send it on
    return new Pair<String, Point>(parts[uuid_index], new Point(lat, lon, accuracy, time));
  }
  
  private Pair<String, Point> formatJSON(String message) throws IOException, ParseException {
    //parse it
    ObjectMapper mapper = new ObjectMapper();
    JsonNode node = mapper.readTree(message);
    //pull out each value
    float lat = floatFormatter.parse(node.get(lat_key).asText()).floatValue();
    float lon = floatFormatter.parse(node.get(lon_key).asText()).floatValue();
    long time = timeFormatter != null ? 
      DateTime.parse(node.get(time_key).asText(), timeFormatter).getMillis() / 1000l : 
      node.get(time_key).asLong();
    int accuracy = (int)Math.ceil(node.get(accuracy_key).asDouble());
    //send it on
    return new Pair<String, Point>(node.get(uuid_key).asText(), new Point(lat, lon, accuracy, time));
  } 
}
