package reporter;

import static org.junit.Assert.*;

import org.junit.Test;

import io.opentraffic.reporter.Formatter;
import io.opentraffic.reporter.Pair;
import io.opentraffic.reporter.Point;

public class FormatterTest {

  @Test
  public void testGetFormatter() {
    Formatter.GetFormatter(",sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss");
    Formatter.GetFormatter("@json@id@latitude@longitude@timestamp@accuracy");
    
    try { Formatter.GetFormatter("%sv%,%a"); fail("Bogus format"); }
    catch(Exception e) { }
    
    try { Formatter.GetFormatter("%json%a%b%c%d"); fail("Bogus format"); }
    catch(Exception e) { }
    
    try { Formatter.GetFormatter("bogus_formatter"); fail("Bogus format"); }
    catch(Exception e) { }
  }

  @Test
  public void testFormat() {
    Formatter psv = Formatter.GetFormatter(",sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss");
    Formatter json = Formatter.GetFormatter("@json@id@la@lo@t@a@yyyy-MM-dd HH:mm:ss");
    
    try {
      Pair<String, Point> pp = psv.format("2017-01-01 06:05:40|w00t||||6.5||||0.0|0.0");
      if(!pp.first.equals("w00t") || !pp.second.equals(new Point(0.0f, 0.0f, 7, 1483250740)))
        fail("Wrong point");
      
      Pair<String, Point> jp = json.format("{\"t\":\"2017-01-01 06:05:40\",\"id\":\"w00t\",\"la\":0.0,\"lo\":0.0,\"a\":6.5}");
      if(!jp.first.equals("w00t") || !jp.second.equals(new Point(0.0f, 0.0f, 7, 1483250740)))
        fail("Wrong point");
    }
    catch(Exception e) {
      fail("Couldn't parse");
    }
  }

}
